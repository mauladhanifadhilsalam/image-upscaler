import io
import time
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import config
from app.main import create_app
from app.upscaler import ResizeUpscaler


def image_bytes(fmt="PNG", size=(32, 24), mode="RGB"):
    buf = io.BytesIO()
    Image.new(mode, size, "red").save(buf, fmt)
    return buf.getvalue()


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(ResizeUpscaler(), tmp_path)) as c:
        yield c


def wait_done(client, job_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] == "done":
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def upload(client, files, scale):
    return client.post("/api/jobs", data={"scale": str(scale)}, files=[("files", f) for f in files])


@pytest.mark.parametrize("scale", [2, 4])
def test_batch_upscale_and_zip(client, scale):
    res = upload(client, [
        ("a.png", image_bytes("PNG"), "image/png"),
        ("b.jpg", image_bytes("JPEG"), "image/jpeg"),
        ("c.webp", image_bytes("WEBP", mode="RGBA"), "image/webp"),
    ], scale)
    assert res.status_code == 201, res.text
    job = wait_done(client, res.json()["id"])
    assert job["progress"] == 1.0
    assert [f["status"] for f in job["files"]] == ["done"] * 3

    first = job["files"][0]
    out = client.get(f"/api/jobs/{job['id']}/files/{first['id']}")
    assert out.status_code == 200
    assert out.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(out.content)).size == (32 * scale, 24 * scale)
    assert f"a_{scale}x.png" in out.headers["content-disposition"]

    original = client.get(f"/api/jobs/{job['id']}/original/{first['id']}")
    assert Image.open(io.BytesIO(original.content)).size == (32, 24)

    archive = zipfile.ZipFile(io.BytesIO(client.get(f"/api/jobs/{job['id']}/zip").content))
    assert sorted(archive.namelist()) == sorted([f"a_{scale}x.png", f"b_{scale}x.jpg", f"c_{scale}x.webp"])


def test_zip_dedupes_names(client):
    res = upload(client, [("x.png", image_bytes(), "image/png")] * 2, 2)
    job = wait_done(client, res.json()["id"])
    archive = zipfile.ZipFile(io.BytesIO(client.get(f"/api/jobs/{job['id']}/zip").content))
    assert sorted(archive.namelist()) == ["x_2x (1).png", "x_2x.png"]


def test_rejects_bad_scale(client):
    assert upload(client, [("a.png", image_bytes(), "image/png")], 3).status_code == 422


def test_rejects_non_image(client):
    assert upload(client, [("a.txt", b"hello", "text/plain")], 2).status_code == 415


def test_rejects_unsupported_format(client):
    assert upload(client, [("a.gif", image_bytes("GIF"), "image/gif")], 2).status_code == 415


def test_rejects_oversized_dimensions(client):
    side = config.MAX_INPUT_SIDE[4] + 1
    assert upload(client, [("big.png", image_bytes(size=(side, 4)), "image/png")], 4).status_code == 422


def test_rejects_too_many_files(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_FILES_PER_JOB", 1)
    res = upload(client, [("a.png", image_bytes(), "image/png")] * 2, 2)
    assert res.status_code == 422


def test_unknown_job(client):
    assert client.get("/api/jobs/nope").status_code == 404


def test_cleanup_removes_expired_jobs(client):
    res = upload(client, [("a.png", image_bytes(), "image/png")], 2)
    job_id = wait_done(client, res.json()["id"])["id"]
    manager = client.app.state.manager
    job_dir = manager.get(job_id).dir
    assert manager.cleanup_expired(now=time.time() + config.JOB_TTL_SECONDS + 1) == 1
    assert not job_dir.exists()
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
