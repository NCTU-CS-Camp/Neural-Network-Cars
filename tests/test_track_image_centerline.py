from PIL import Image

from pipeline.track import AlphaCollisionMask
from pipeline.track import _image_centerline


def test_image_centerline_uses_alpha_road_middle() -> None:
    alpha = Image.new("L", (50, 50), 0)
    for x in range(10, 31):
        for y in range(50):
            alpha.putpixel((x, y), 255)

    mask = AlphaCollisionMask(alpha=alpha)
    centered = _image_centerline(
        polyline=[(12.0, 10.0), (12.0, 40.0)],
        mask=mask,
        closed_loop=False,
        cell_size=50,
    )

    assert centered == [(20.0, 10.0), (20.0, 40.0)]
