"""
Download one KITTI raw drive: front camera + GPS/IMU (OXTS) only.
KITTI raw data: CC BY-NC-SA 3.0, Geiger et al., "Vision meets Robotics: The KITTI Dataset", IJRR 2013.
"""
import argparse
import io
import os
import struct
import urllib.request
import zipfile
import zlib

import cv2

BASE = "https://s3.eu-central-1.amazonaws.com/avg-kitti/raw_data"
UA = {"User-Agent": "motorsport-pipeline-sample/0.1"}


class HttpFile(io.RawIOBase):
    """Seekable file over HTTP Range requests, so we only fetch the zip parts we need."""

    def __init__(self, url):
        self.url = url
        req = urllib.request.Request(url, method="HEAD", headers=UA)
        self.size = int(urllib.request.urlopen(req).headers["Content-Length"])
        self.pos = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = [offset, self.pos + offset, self.size + offset][whence]
        return self.pos

    def readinto(self, buf):
        if self.pos >= self.size:
            return 0
        end = min(self.pos + len(buf), self.size) - 1
        req = urllib.request.Request(self.url, headers={**UA, "Range": f"bytes={self.pos}-{end}"})
        data = urllib.request.urlopen(req).read()
        buf[:len(data)] = data
        self.pos += len(data)
        return len(data)


def group_spans(infos, max_gap=1 << 20):
    spans = [[infos[0]]]
    for info in infos[1:]:
        prev = spans[-1][-1]
        if info.header_offset - (prev.header_offset + prev.compress_size) > max_gap:
            spans.append([])
        spans[-1].append(info)
    return spans


def extract(blob, off, info):
    # Local header: 30 bytes + file name + extra field, then the data
    name_len, extra_len = struct.unpack("<HH", blob[off + 26:off + 30])
    data = blob[off + 30 + name_len + extra_len:][:info.compress_size]
    if info.compress_type == zipfile.ZIP_DEFLATED:
        return zlib.decompress(data, -15)
    return data


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--drive", default="2011_09_26_drive_0015")
    p.add_argument("--out", default="sample-data")
    args = p.parse_args()

    date = args.drive[:10]
    out_dir = os.path.join(args.out, args.drive)
    url = f"{BASE}/{args.drive}/{args.drive}_sync.zip"

    # Read only the zip's file list (at the end of the archive)
    http = HttpFile(url)
    wanted = [i for i in zipfile.ZipFile(http).infolist()
              if ("/image_02/" in i.filename or "/oxts/" in i.filename) and not i.is_dir()]
    wanted.sort(key=lambda i: i.header_offset)

    # Members sit next to each other, so fetch them in a few big ranges
    for span in group_spans(wanted):
        start = span[0].header_offset
        end = span[-1].header_offset + span[-1].compress_size + 1024
        print(f"fetching {len(span)} files ({(end - start) / 1e6:.0f} MB)")
        http.seek(start)
        blob = http.read(end - start)
        for info in span:
            dest = os.path.join(out_dir, info.filename.split(f"{args.drive}_sync/")[1])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(extract(blob, info.header_offset - start, info))

    # Also build an mp4 (10 fps) so the CV worker can read it like any video
    img_dir = os.path.join(out_dir, "image_02", "data")
    frames = sorted(os.listdir(img_dir))
    h, w = cv2.imread(os.path.join(img_dir, frames[0])).shape[:2]
    mp4 = os.path.join(out_dir, "front.mp4")
    writer = cv2.VideoWriter(mp4, cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
    for f in frames:
        writer.write(cv2.imread(os.path.join(img_dir, f)))
    writer.release()
    print(f"wrote {mp4} ({len(frames)} frames), telemetry in {out_dir}/oxts")


if __name__ == "__main__":
    main()
