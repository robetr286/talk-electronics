from talk_electronic.utils.ignore_filter import filter_detections_by_polygons


def test_filter_removes_detection_inside_polygon():
    # image 100x100
    img_shape = (100, 100)

    # One detection fully inside the polygon
    detections = [{"id": "d1", "bbox": [20, 20, 20, 20], "label": "wire"}]

    # Polygon covering area including bbox (square covering 10..60 in both dims)
    ignore_regions = [{"type": "polygon", "points": [[10, 10], [60, 10], [60, 60], [10, 60]]}]

    filtered, removed = filter_detections_by_polygons(detections, ignore_regions, img_shape, iou_threshold=0.1)

    assert removed == 1
    assert filtered == []


def test_filter_keeps_detection_outside_polygon():
    img_shape = (100, 100)
    detections = [{"id": "d1", "bbox": [70, 70, 10, 10], "label": "wire"}]
    ignore_regions = [{"type": "polygon", "points": [[10, 10], [60, 10], [60, 60], [10, 60]]}]

    filtered, removed = filter_detections_by_polygons(detections, ignore_regions, img_shape, iou_threshold=0.1)
    assert removed == 0
    assert len(filtered) == 1
