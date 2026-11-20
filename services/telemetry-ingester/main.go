// Reads telemetry and CV events from Kafka and writes them to ClickHouse in small batches.
package main

import (
	"context"
	"encoding/json"
	"log"
	"os"
	"os/signal"
	"sort"
	"strings"
	"syscall"
	"time"

	"github.com/ClickHouse/clickhouse-go/v2"
	"github.com/ClickHouse/clickhouse-go/v2/lib/driver"
	"github.com/twmb/franz-go/pkg/kgo"
)

const (
	topicTelemetry = "motorsport.telemetry"
	topicCV        = "motorsport.cv.events"
)

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	flushEvery, _ := time.ParseDuration(env("FLUSH_INTERVAL", "50ms"))

	ch, err := clickhouse.Open(&clickhouse.Options{
		Addr: []string{env("CLICKHOUSE_ADDR", "localhost:9000")},
		Auth: clickhouse.Auth{
			Database: env("CLICKHOUSE_DB", "motorsport"),
			Username: env("CLICKHOUSE_USER", "motorsport"),
			Password: env("CLICKHOUSE_PASSWORD", "motorsport"),
		},
	})
	if err != nil {
		log.Fatalf("clickhouse: %v", err)
	}
	if err := ch.Ping(ctx); err != nil {
		log.Fatalf("clickhouse ping: %v", err)
	}

	kc, err := kgo.NewClient(
		kgo.SeedBrokers(strings.Split(env("KAFKA_BROKERS", "localhost:19092"), ",")...),
		kgo.ConsumerGroup(env("KAFKA_GROUP", "motorsport-ingester")),
		kgo.ConsumeTopics(topicTelemetry, topicCV),
		kgo.DisableAutoCommit(), // commit only after ClickHouse has the rows
	)
	if err != nil {
		log.Fatalf("kafka: %v", err)
	}
	defer kc.Close()

	log.Printf("ingester running, flush every %s", flushEvery)
	stats := newStats()
	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()

	for ctx.Err() == nil {
		// Wait for records, at most one flush interval
		pollCtx, cancel := context.WithTimeout(ctx, flushEvery)
		fetches := kc.PollFetches(pollCtx)
		cancel()
		fetches.EachError(func(t string, p int32, err error) {
			if err != context.DeadlineExceeded && err != context.Canceled {
				log.Printf("fetch error %s/%d: %v", t, p, err)
			}
		})

		var tel []Telemetry
		var cv []CVEvent
		var records []*kgo.Record
		fetches.EachRecord(func(r *kgo.Record) {
			records = append(records, r)
			switch r.Topic {
			case topicTelemetry:
				var m Telemetry
				if err := json.Unmarshal(r.Value, &m); err != nil {
					log.Printf("bad telemetry msg: %v", err)
					return
				}
				tel = append(tel, m)
			case topicCV:
				var m CVEvent
				if err := json.Unmarshal(r.Value, &m); err != nil {
					log.Printf("bad cv msg: %v", err)
					return
				}
				cv = append(cv, m)
			}
		})
		if len(records) == 0 {
			select {
			case <-ticker.C:
				stats.report()
			default:
			}
			continue
		}

		if err := insertTelemetry(ctx, ch, tel); err != nil {
			log.Printf("insert telemetry: %v", err) // not committed, will be re-read
			continue
		}
		if err := insertCV(ctx, ch, cv); err != nil {
			log.Printf("insert cv: %v", err)
			continue
		}
		if err := kc.CommitRecords(ctx, records...); err != nil {
			log.Printf("commit: %v", err)
		}

		// Latency: Kafka write time -> row in ClickHouse
		now := time.Now()
		for _, r := range records {
			stats.add(now.Sub(r.Timestamp))
		}
		select {
		case <-ticker.C:
			stats.report()
		default:
		}
	}
	stats.report()
	log.Print("ingester stopped")
}

func ms(v int64) time.Time { return time.UnixMilli(v) }

func insertTelemetry(ctx context.Context, ch driver.Conn, rows []Telemetry) error {
	if len(rows) == 0 {
		return nil
	}
	b, err := ch.PrepareBatch(ctx, "INSERT INTO telemetry")
	if err != nil {
		return err
	}
	for _, r := range rows {
		if err := b.Append(r.RunID, ms(r.TsMs), r.SpeedKmh, r.YawRateDegS, r.AccelLong, r.AccelLat,
			r.HeadingDeg, r.Lat, r.Lon, r.Alt, r.SteeringDeg, r.Throttle, r.Brake); err != nil {
			return err
		}
	}
	return b.Send()
}

func insertCV(ctx context.Context, ch driver.Conn, rows []CVEvent) error {
	if len(rows) == 0 {
		return nil
	}
	b, err := ch.PrepareBatch(ctx, "INSERT INTO cv_events")
	if err != nil {
		return err
	}
	for _, r := range rows {
		if err := b.Append(r.RunID, ms(r.TsMs), r.FrameIdx, r.InferenceMs, r.NDetections, r.NHazards,
			r.MinHazardDistM, r.LateralOffset, r.ApexDist, r.YawRateDegS, r.SlipAngleDeg, r.SpeedEstKmh,
			string(r.Detections)); err != nil {
			return err
		}
	}
	return b.Send()
}

// Simple latency stats, printed every 10s
type stats struct{ lat []time.Duration }

func newStats() *stats { return &stats{} }

func (s *stats) add(d time.Duration) { s.lat = append(s.lat, d) }

func (s *stats) report() {
	if len(s.lat) == 0 {
		return
	}
	sort.Slice(s.lat, func(i, j int) bool { return s.lat[i] < s.lat[j] })
	p := func(q float64) time.Duration { return s.lat[int(q*float64(len(s.lat)-1))] }
	log.Printf("ingested %d rows, kafka->clickhouse p50 %s p95 %s max %s",
		len(s.lat), p(0.5).Round(time.Millisecond/10), p(0.95).Round(time.Millisecond/10), p(1).Round(time.Millisecond/10))
	s.lat = s.lat[:0]
}
