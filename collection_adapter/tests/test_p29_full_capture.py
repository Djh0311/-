import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from collection_adapter.p26_identification import IdentificationWindow
from collection_adapter.p26_identification_host import IdentificationAddon
from collection_adapter.p29_full_capture import FullCapture


class FullCaptureTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.root.chmod(0o700)
        window = IdentificationWindow("Synthetic shop", duration_seconds=None)
        window.start_once()
        self.addon = IdentificationAddon(window, detached_analysis=False)
        self.addon.full_capture = FullCapture(self.root)

    def flow(self, identity, path, content_type):
        return SimpleNamespace(
            id=identity,
            client_conn=SimpleNamespace(sni="shop.example"),
            request=SimpleNamespace(method="POST", host="shop.example", path=path, stream=None),
            response=SimpleNamespace(status_code=200, headers={
                "content-type": content_type, "content-encoding": "identity",
                "cookie": "secret"}, stream=None))

    def test_json_is_saved_without_query_or_headers_and_images_are_skipped(self):
        hello = SimpleNamespace(client_hello=SimpleNamespace(sni="shop.example"), ignore_connection=True)
        self.addon.tls_clienthello(hello)
        self.assertFalse(hello.ignore_connection)
        flow = self.flow("synthetic-json", "/weapp/v1/poi/food?token=secret", "application/json")
        self.addon.requestheaders(flow)
        self.assertEqual(flow.request.stream(b"poi=1"), b"poi=1")
        self.addon.responseheaders(flow)
        body = b'{"code":0}'
        self.assertEqual(flow.response.stream(body), body)
        self.addon.response(flow)
        saved = self.root / "captured-http"
        meta = json.loads((saved / "000001.json").read_text())
        self.assertEqual(meta["path"], "/weapp/v1/poi/food")
        self.assertNotIn("token", json.dumps(meta))
        self.assertNotIn("secret", json.dumps(meta))
        self.assertEqual((saved / "000001.response").read_bytes(), body)
        self.assertEqual((saved / "000001.request").read_bytes(), b"poi=1")
        image = self.flow("synthetic-image", "/picture.png", "image/jpeg")
        self.addon.requestheaders(image)
        self.addon.responseheaders(image)
        self.assertIs(image.response.stream, True)
        self.addon.response(image)
        self.assertFalse((saved / "000002.json").exists())
        self.assertEqual(self.addon.full_capture.skipped_media, 1)
        self.assertEqual(self.addon.full_capture.saved, 1)

    def test_image_telemetry_and_websocket_hosts_stay_on_the_original_connection(self):
        from collection_adapter.p29_full_capture import passthrough_sni
        for host in ("p0.meituan.net", "img.meituan.net", "lx0.meituan.com",
                     "wss.neixin.cn", "mmbiz.qpic.cn", "catfront.dianping.com"):
            hello = SimpleNamespace(client_hello=SimpleNamespace(sni=host), ignore_connection=False)
            self.addon.tls_clienthello(hello)
            self.assertTrue(hello.ignore_connection, host)
            self.assertTrue(passthrough_sni(host), host)
        product = SimpleNamespace(client_hello=SimpleNamespace(sni="hcapi-wx.waimai.meituan.com"),
                                  ignore_connection=True)
        self.addon.tls_clienthello(product)
        self.assertFalse(product.ignore_connection)


if __name__ == "__main__":
    unittest.main()
