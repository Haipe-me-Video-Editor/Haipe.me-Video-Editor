import cv2
import numpy as np

from editor import retouch


def _landmarks():
    """A synthetic face: oval, eyes, lower lids, brows and lips at plausible places in a 600x800 frame."""
    P = np.tile(np.float32([300, 400]), (478, 1))

    def ring(idx, c, r, a0=0.0, a1=2 * np.pi):
        t = np.linspace(a0, a1, len(idx), endpoint=a1 - a0 < 2 * np.pi)
        P[idx] = np.stack([c[0] + r[0] * np.cos(t), c[1] + r[1] * np.sin(t)], 1)

    ring(retouch.FACE_OVAL, (300, 400), (200, 270))
    P[454], P[234] = (500, 400), (100, 400)
    for k, cx in (("r", 220), ("l", 380)):
        ring(retouch.EYE[k], (cx, 330), (40, 12))
        ring(retouch.LOWER_LID[k], (cx, 330), (40, 12), np.pi, 0)  # outer corner to inner, along the bottom
        P[retouch.LOWER_LID[k], 1] = 330 + np.abs(P[retouch.LOWER_LID[k], 1] - 330)
        ring(retouch.BROW[k], (cx, 285), (45, 6))
    ring(retouch.LIPS, (300, 560), (55, 18))
    return P


def _face(dark=40):
    img = np.full((800, 600, 3), (120, 150, 190), np.uint8)  # warm skin (BGR)
    img[352:372, 195:245] -= dark  # shadow under the right eye
    return img


def test_under_eye_shadow_is_lifted_but_not_all_the_way():
    img, P = _face(), _landmarks()
    out = retouch.retouch_frame(img, P)
    before, after = img[362, 220].mean(), out[362, 220].mean()
    assert after > before + 8 and after < img[420, 220].mean()


def test_colour_is_kept_and_cheek_is_untouched():
    img, P = _face(), _landmarks()
    out = retouch.retouch_frame(img, P)
    hue = lambda px: cv2.cvtColor(px.reshape(1, 1, 3), cv2.COLOR_BGR2HSV)[0, 0, 0]
    assert abs(int(hue(out[362, 220])) - int(hue(img[362, 220]))) <= 1
    assert np.abs(out[450:500, 150:250].astype(int) - img[450:500, 150:250]).max() <= 1
    assert (out[:, :40] == img[:, :40]).all()  # outside the face nothing changes


def test_small_dark_mark_is_removed_and_glasses_rims_are_protected():
    img, P = _face(), _landmarks()
    img[440:444, 380:384] -= 30  # a mark on the cheek
    img[340:343, 180:260] = 20  # a glasses rim through the under-eye band
    out = retouch.retouch_frame(img, P)
    assert out[442, 382].mean() > img[442, 382].mean() + 15
    assert abs(int(out[341, 220].mean()) - 20) <= 3


def test_no_face_means_no_change():
    img = _face()
    assert retouch.retouch_frame(img, None) is img


def test_smoother_holds_through_two_missed_frames():
    s, P = retouch.Smoother(), _landmarks()
    assert s.update(P) is P
    assert s.update(None) is not None and s.update(None) is not None
    assert s.update(None) is None
