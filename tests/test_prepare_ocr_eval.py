from scripts.prepare_ocr_eval import parse_labelstudio_task


def test_parse_designator_value_from_meta():
    # minimal task with a rectangle annotation that includes meta.text with designator and value
    task = {
        "data": {"image": "1.png"},
        "annotations": [
            {
                "result": [
                    {
                        "value": {"x": 10, "y": 20, "width": 5, "height": 5, "rectanglelabels": ["resistor"]},
                        "meta": {"text": ["designator=R1 type=resistor value=10k tolerance=unknown"]},
                    }
                ]
            }
        ],
    }

    image_ref, components = parse_labelstudio_task(task)

    assert image_ref == "1.png"
    assert isinstance(components, list)
    # We expect one component and that it contains parsed designator/value
    assert len(components) == 1
    comp = components[0]
    assert comp.get("label") == "R1"
    assert comp.get("value") == "10k"
