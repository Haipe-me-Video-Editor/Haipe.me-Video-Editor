from editor import voice


def test_default_chain_is_e3():
    c = voice.chain(model="m.rnnn")
    assert c.startswith("aresample=48000,highpass=f=70:p=2,bandreject=f=50:t=q:w=8,bandreject=f=100:t=q:w=8,"
                        "bandreject=f=1615:t=q:w=12,arnndn=m=m.rnnn:mix=0.9,afftdn=nr=18:nf=-55:tn=1")
    assert "aexciter=" in c and "equalizer=f=3200:t=q:w=1.2:g=2.0" in c and "ratio=1.7" in c
    assert "deesser" not in c


def test_a_voice_profile_overrides_and_switches_steps_off():
    c = voice.chain({"denoise": 0, "residual_nr": 0, "notches": [], "exciter": 0, "comp_ratio": 1}, model="m.rnnn")
    assert not any(x in c for x in ("arnndn", "afftdn", "bandreject", "aexciter", "acompressor"))
