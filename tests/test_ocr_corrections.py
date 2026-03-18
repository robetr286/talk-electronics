import json

from talk_electronic import ocr_corrections


def test_summarize(tmp_path, monkeypatch):
    # prepare fake corrections directory
    corr_dir = tmp_path / "correct"
    corr_dir.mkdir()
    data1 = {"request_id": "a", "corrections": [{"component": "R1", "value": "10k"}]}
    data2 = {
        "request_id": "b",
        "corrections": [{"component": "R1", "value": "22k"}, {"component": "C1", "value": "100nF"}],
    }
    (corr_dir / "a_corrections.json").write_text(json.dumps(data1), encoding="utf-8")
    (corr_dir / "b_corrections.json").write_text(json.dumps(data2), encoding="utf-8")

    summary = ocr_corrections.summarize_corrections(directory=corr_dir)
    assert summary["total_files"] == 2
    assert summary["total_entries"] == 3
    assert summary["component_counts"]["R1"] == 2
    assert summary["component_counts"]["C1"] == 1
    assert summary["value_counts"]["10k"] == 1
    assert summary["value_counts"]["22k"] == 1
    assert summary["value_counts"]["100nF"] == 1
