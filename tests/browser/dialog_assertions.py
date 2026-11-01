def assert_centered(dialog):
    dialog.wait_for(state="visible")
    original = dialog.page.viewport_size
    try:
        for viewport in [original, {"width": 922, "height": 768}, {"width": 390, "height": 844}]:
            dialog.page.set_viewport_size(viewport)
            dialog.page.wait_for_function(
                """() => [...document.querySelectorAll('dialog[open]')].every(dialog => {
                  const rect = dialog.getBoundingClientRect();
                  return Math.abs(rect.x + rect.width / 2 - innerWidth / 2) <= 2
                    && Math.abs(rect.y + rect.height / 2 - innerHeight / 2) <= 2
                    && rect.x >= 0 && rect.y >= 0
                    && rect.right <= innerWidth && rect.bottom <= innerHeight;
                })""",
                timeout=3000,
            )
    finally:
        dialog.page.set_viewport_size(original)
    assert dialog.is_visible()


def assert_no_review_metadata(dialog):
    for label in ["S.NO", "Serial no", "Validation", "Validated by", "Validated on", "Validation date"]:
        assert dialog.get_by_text(label, exact=True).count() == 0
