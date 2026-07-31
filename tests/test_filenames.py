from app.utils.filenames import safe_filename_component


def test_safe_filename_component_handles_windows_rules() -> None:
    assert safe_filename_component(
        '  product:hero?  ',
        fallback="slice",
    ) == "product_hero_"
    assert safe_filename_component("CON", fallback="slice") == "_CON"
    assert safe_filename_component("... ", fallback="slice") == "slice"
