from editor import extras


def test_sfx_listing_reads_titles_and_preview_urls():
    page = ('<div class="item-grid__item"><div data-audio-player-preview-url-value='
            '"https://assets.mixkit.co/active_storage/sfx/1489/1489-preview.mp3"></div>'
            '<h2 class="item-grid-card__title">Air woosh</h2></div>'
            '<div class="item-grid__item"><h2 class="item-grid-card__title">No audio</h2></div>')
    assert extras._sfx_listing(page) == [("1489", "Air woosh",
                                          "https://assets.mixkit.co/active_storage/sfx/1489/1489-preview.mp3")]


def test_every_model_has_a_free_source_and_a_cache_file():
    for name, (url, file) in extras.MODELS.items():
        assert url.startswith(("https://huggingface.co/", "https://storage.googleapis.com/mediapipe-models/"))
        assert (extras.MODELS_DIR / file).name == file and file.endswith((".onnx", ".tflite", ".task"))
