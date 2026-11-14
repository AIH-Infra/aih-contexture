# Copyright (c) 2024 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import numpy as np

def iou(box1, box2):
    """Compute the Intersection over Union (IoU) of two bounding boxes."""
    x1, y1, x2, y2 = box1
    x1_p, y1_p, x2_p, y2_p = box2

    # Compute the intersection coordinates
    x1_i = max(x1, x1_p)
    y1_i = max(y1, y1_p)
    x2_i = min(x2, x2_p)
    y2_i = min(y2, y2_p)

    # Compute the area of intersection
    inter_area = max(0, x2_i - x1_i + 1) * max(0, y2_i - y1_i + 1)

    # Compute the area of both bounding boxes
    box1_area = (x2 - x1 + 1) * (y2 - y1 + 1)
    box2_area = (x2_p - x1_p + 1) * (y2_p - y1_p + 1)

    # Compute the IoU
    iou_value = inter_area / float(box1_area + box2_area - inter_area)

    return iou_value

def nms(boxes, iou_same=0.6, iou_diff=0.95):
    """Perform Non-Maximum Suppression (NMS) with different IoU thresholds for same and different classes."""
    # Extract class scores
    scores = boxes[:, 1]

    # Sort indices by scores in descending order
    indices = np.argsort(scores)[::-1]
    selected_boxes = []

    while len(indices) > 0:
        current = indices[0]
        current_box = boxes[current]
        current_class = current_box[0]
        current_box[1]
        current_coords = current_box[2:]

        selected_boxes.append(current)
        indices = indices[1:]

        filtered_indices = []
        for i in indices:
            box = boxes[i]
            box_class = box[0]
            box_coords = box[2:]
            iou_value = iou(current_coords, box_coords)
            threshold = iou_same if current_class == box_class else iou_diff

            # If the IoU is below the threshold, keep the box
            if iou_value < threshold:
                filtered_indices.append(i)
        indices = filtered_indices
    return selected_boxes

def is_contained(box1, box2):
    """Check if box1 is contained within box2."""
    _, _, x1, y1, x2, y2 = box1
    _, _, x1_p, y1_p, x2_p, y2_p = box2
    box1_area = (x2 - x1) * (y2 - y1)
    xi1 = max(x1, x1_p)
    yi1 = max(y1, y1_p)
    xi2 = min(x2, x2_p)
    yi2 = min(y2, y2_p)
    inter_width = max(0, xi2 - xi1)
    inter_height = max(0, yi2 - yi1)
    intersect_area = inter_width * inter_height
    iou = intersect_area / box1_area if box1_area > 0 else 0
    return iou >= 0.9

def check_containment(boxes, formula_index=None, category_index=None, mode=None):
    """Check containment relationships among boxes."""
    n = len(boxes)
    contains_other = np.zeros(n, dtype=int)
    contained_by_other = np.zeros(n, dtype=int)

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if formula_index is not None:
                if boxes[i][0] == formula_index and boxes[j][0] != formula_index:
                    continue
            if category_index is not None and mode is not None:
                if mode == "large" and boxes[j][0] == category_index:
                    if is_contained(boxes[i], boxes[j]):
                        contained_by_other[i] = 1
                        contains_other[j] = 1
                if mode == "small" and boxes[i][0] == category_index:
                    if is_contained(boxes[i], boxes[j]):
                        contained_by_other[i] = 1
                        contains_other[j] = 1
            else:
                if is_contained(boxes[i], boxes[j]):
                    contained_by_other[i] = 1
                    contains_other[j] = 1
    return contains_other, contained_by_other
