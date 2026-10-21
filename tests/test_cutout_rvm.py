import numpy as np

from editor import cutout


def test_fill_holes_closes_holes_inside_the_silhouette_but_not_the_background():
    a = np.zeros((400, 200), np.float32)
    a[100:400, 40:160] = 1          # a body running off the bottom edge
    a[200:240, 80:120] = 0          # a see-through patch in the shirt
    a[100:180, 0:20] = 0            # background beside the body stays background
    out = cutout.fill_holes(a)
    assert out[220, 100] > 0.9      # the hole is solid now
    assert out[50, 100] < 0.05 and out[150, 5] < 0.05


def test_default_engine_is_rvm_and_modnet_is_the_fallback(monkeypatch):
    monkeypatch.delenv("EDITOR_MATTE", raising=False)
    assert cutout.engine() == "rvm"
    monkeypatch.setenv("EDITOR_MATTE", "modnet")
    assert cutout.engine() == "modnet"


def _classes(h=512, w=288):
    """Six MediaPipe-style class confidences: background everywhere to start with."""
    cm = np.zeros((6, h, w), np.float32)
    cm[0] = 1
    return cm


def test_the_gate_stands_aside_around_the_head_and_for_what_the_hands_hold():
    cm = _classes()
    cm[3, 60:160, 100:190] = 1          # face
    cm[1, 30:70, 90:200] = 1            # hair on top
    cm[2, 400:440, 120:170] = 1         # a hand low in the frame
    fg = np.zeros((512, 288), np.uint8)
    fg[30:512, 80:210] = 1              # RVM: the person ...
    fg[340:420, 170:230] = 1            # ... a card held out beside the hand (a fifth of the width) ...
    fg[180:240, 0:80] = 1               # ... and the chair beside the shoulders, joined to the body
    zone = cutout.protected(cm, fg)
    assert zone[50, 95] > 0.9           # hair edge
    assert zone[100, 194] > 0.5         # just outside the face: where the glasses' arms run
    assert zone[380, 225] > 0.9         # the far end of the held card
    assert zone[210, 10] < 0.05         # the chair stays gated
    assert zone[480, 20] < 0.05         # plain background stays gated


def test_the_neck_does_not_count_as_a_hand():
    cm = _classes()
    cm[3, 60:160, 100:190] = 1          # face
    cm[2, 160:200, 120:170] = 1         # neck skin just under the chin
    fg = np.zeros((512, 288), np.uint8)
    fg[60:512, 60:230] = 1
    fg[170:230, 0:60] = 1               # a chair back touching the shoulder
    assert cutout.protected(cm, fg)[200, 10] < 0.05


def test_fine_alpha_keeps_the_full_size_edge_inside_the_clean_shape():
    from editor.fx import _cutkit as K
    W, H = 540, 960
    small = np.zeros((H // 2, W // 2), np.uint8)
    small[120:480, 70:200] = 255         # the clean matte: a body (its hole already filled)
    full = np.zeros((H, W), np.float32)
    full[240:960, 140:400] = 1
    full[500:540, 250:290] = 0           # a hole the clean matte filled
    full[226:240, 160:380] = 0.5         # soft hair just above the body: kept as soft
    full[40:60, 10:30] = 1               # a speck the clean matte dropped: stays dropped
    a = K.fine_alpha(small, full)
    assert a[520, 270] > 0.9
    assert 0.3 < a[230, 270] < 0.7
    assert a[50, 20] < 0.05
