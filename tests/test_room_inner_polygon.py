from EstiSketch.Canvas.canvas_geometry import CanvasGeometryMixin as G


def area(p):
    return abs(sum(p[i][0]*p[(i+1) % len(p)][1]-p[(i+1) % len(p)][0]*p[i][1]
                   for i in range(len(p))))/2


def test_inset_square_both_orientations():
    sq = [(0, 0), (100, 0), (100, 100), (0, 100)]
    for poly in (sq, sq[::-1]):
        out = G._inset_polygon(poly, [4.0]*4)
        assert abs(area(out) - 92*92) < 1e-6
        assert all(4-1e-6 <= x <= 96+1e-6 and 4-1e-6 <= y <= 96+1e-6 for x, y in out)


def test_inset_mixed_thickness():
    sq = [(0, 0), (100, 0), (100, 100), (0, 100)]
    out = G._inset_polygon(sq, [8, 2, 2, 2])
    xs = sorted(p[0] for p in out); ys = sorted(p[1] for p in out)
    assert (xs[0], xs[-1], ys[0], ys[-1]) == (2, 98, 8, 98)
