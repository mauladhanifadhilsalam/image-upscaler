import anyio
import httpx
import pytest
from mcp.client import Client
from PIL import Image

from agent.client import UpscalerClient, UpscalerError
from agent.mcp_server import create_server
from app.main import create_app
from app.upscaler import ResizeUpscaler

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def make_client(tmp_path):
    """Factory for UpscalerClients talking to an in-process API (Lanczos upscaler)."""
    app = create_app(ResizeUpscaler(), tmp_path / "storage")
    async with app.router.lifespan_context(app):
        def factory():
            http = httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test")
            return UpscalerClient(http)
        yield factory


@pytest.fixture
def images(tmp_path):
    folder = tmp_path / "pics"
    folder.mkdir()
    paths = []
    for name, fmt in [("cat.png", "PNG"), ("dog.jpg", "JPEG")]:
        path = folder / name
        Image.new("RGB", (30, 20), "blue").save(path, fmt)
        paths.append(path)
    return paths


@pytest.fixture
async def mcp(make_client):
    async with Client(create_server(make_client)) as client:
        yield client


async def test_lists_tools(mcp):
    tools = {t.name for t in (await mcp.list_tools()).tools}
    assert tools == {"upscale_images", "get_job_status", "download_results", "upscaler_info"}


async def test_info(mcp):
    res = await mcp.call_tool("upscaler_info", {})
    assert not res.is_error
    assert res.structured_content["upscaler"] == "lanczos"
    assert res.structured_content["limits"]["max_files"] == 20


@pytest.mark.parametrize("scale", [2, 4])
async def test_upscale_saves_next_to_inputs(mcp, images, scale):
    res = await mcp.call_tool("upscale_images", {"paths": [str(p) for p in images], "scale": scale})
    assert not res.is_error, res.content
    out = res.structured_content
    assert out["status"] == "done"
    saved = [r["output"] for r in out["results"]]
    assert saved == [str(images[0].with_name(f"cat_{scale}x.png")), str(images[1].with_name(f"dog_{scale}x.jpg"))]
    for path in saved:
        assert Image.open(path).size == (30 * scale, 20 * scale)


async def test_upscale_to_output_dir(mcp, images, tmp_path):
    out_dir = tmp_path / "results"
    res = await mcp.call_tool("upscale_images", {"paths": [str(images[0])], "scale": 4, "output_dir": str(out_dir)})
    assert res.structured_content["results"][0]["output"] == str(out_dir / "cat_4x.png")


async def test_refuses_to_overwrite(mcp, images):
    images[0].with_name("cat_2x.png").write_bytes(b"keep me")
    res = await mcp.call_tool("upscale_images", {"paths": [str(images[0])], "scale": 2})
    assert res.is_error
    assert "already exists" in res.content[0].text
    assert images[0].with_name("cat_2x.png").read_bytes() == b"keep me"

    res = await mcp.call_tool("upscale_images", {"paths": [str(images[0])], "scale": 2, "overwrite": True})
    assert not res.is_error
    assert Image.open(images[0].with_name("cat_2x.png")).size == (60, 40)


async def test_rejects_bad_inputs(mcp, tmp_path):
    text = tmp_path / "notes.txt"
    text.write_text("hi")
    for paths, message in [
        ([str(tmp_path / "missing.png")], "File not found"),
        ([str(text)], "Not an image"),
        (["relative.png"], "absolute path"),
    ]:
        res = await mcp.call_tool("upscale_images", {"paths": paths})
        assert res.is_error
        assert message in res.content[0].text


async def test_rejects_bad_scale(mcp, images):
    res = await mcp.call_tool("upscale_images", {"paths": [str(images[0])], "scale": 3})
    assert res.is_error


async def test_timeout_then_poll_and_download(mcp, images, tmp_path):
    res = await mcp.call_tool("upscale_images", {"paths": [str(images[0])], "timeout_seconds": 0})
    job_id = res.structured_content["job_id"]

    for _ in range(50):
        status = (await mcp.call_tool("get_job_status", {"job_id": job_id})).structured_content
        if status["status"] == "done":
            break
        await anyio.sleep(0.05)
    assert status["status"] == "done"

    out_dir = tmp_path / "later"
    res = await mcp.call_tool("download_results", {"job_id": job_id, "output_dir": str(out_dir)})
    assert res.structured_content["saved"] == [str(out_dir / "cat_2x.png")]


async def test_unknown_job(mcp):
    res = await mcp.call_tool("get_job_status", {"job_id": "nope"})
    assert res.is_error
    assert "404" in res.content[0].text


async def test_api_down_gives_helpful_error(tmp_path):
    client = UpscalerClient(base_url="http://127.0.0.1:9")
    with pytest.raises(UpscalerError, match="Cannot reach the upscaler API"):
        await client.info()
    await client.aclose()
