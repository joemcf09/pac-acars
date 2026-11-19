"""Fleet display photos should be resized instead of sending multi-megabyte originals."""
from io import BytesIO

from flask import Flask
from PIL import Image

import image_delivery


def test_fleet_photo_is_a_bounded_webp(tmp_path):
    static = tmp_path / "static"
    (static / "fleet").mkdir(parents=True)
    (tmp_path / "data").mkdir()
    fleet_photos = tmp_path / "fleet_photos"
    fleet_photos.mkdir()
    source = fleet_photos / "B77F.png"
    Image.new("RGB", (2400, 1600), "red").save(source)
    app = Flask(__name__, static_folder=str(static))
    image_delivery.register(app, tmp_path / "data", fleet_photos, {"B77F": {}})

    with app.test_client() as client:
        response = client.get("/media/image?src=/api/fleet/B77F/photo&w=800&pipeline=2")
        assert response.status_code == 200
        assert response.mimetype == "image/webp"
        assert len(response.data) < source.stat().st_size
        with Image.open(BytesIO(response.data)) as photo:
            assert max(photo.size) == 800

        cached = client.get("/media/image?src=/api/fleet/B77F/photo&w=800&pipeline=2")
        assert cached.status_code == 200
        assert cached.data == response.data
