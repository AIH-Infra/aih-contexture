# Copyright (c) Opendatalab. All rights reserved.
# copyright (c) 2020 PaddlePaddle Authors. All Rights Reserve.
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
import re
import numpy as np
import torch


class BaseRecLabelDecode(object):
    """ Convert between text-label and text-index """

    def __init__(self,
                 character_dict_path=None,
                 use_space_char=False):

        self.beg_str = "sos"
        self.end_str = "eos"
        self.reverse = False
        self.character_str = []

        if character_dict_path is None:
            self.character_str = "0123456789abcdefghijklmnopqrstuvwxyz"
            dict_character = list(self.character_str)
        else:
            with open(character_dict_path, "rb") as fin:
                lines = fin.readlines()
                for line in lines:
                    line = line.decode('utf-8').strip("\n").strip("\r\n")
                    self.character_str.append(line)
            if use_space_char:
                self.character_str.append(" ")
            dict_character = list(self.character_str)
            if "arabic" in character_dict_path:
                self.reverse = True

        dict_character = self.add_special_char(dict_character)
        self.dict = {}
        for i, char in enumerate(dict_character):
            self.dict[char] = i
        self.character = np.array(dict_character)

    def pred_reverse(self, pred):
        pred_re = []
        c_current = ""
        for c in pred:
            if not bool(re.search("[a-zA-Z0-9 :*./%+-]", c)):
                if c_current != "":
                    pred_re.append(c_current)
                pred_re.append(c)
                c_current = ""
            else:
                c_current += c
        if c_current != "":
            pred_re.append(c_current)

        return "".join(pred_re[::-1])

    def add_special_char(self, dict_character):
        return dict_character

    def get_word_info(self, text, selection):
        """
        Group the decoded characters and record the corresponding decoded positions.

        Args:
            text: the decoded text
            selection: the bool array that identifies which columns of features are decoded as non-separated characters
        Returns:
            word_list: list of the grouped words
            word_col_list: list of decoding positions corresponding to each character in the grouped word
            state_list: list of marker to identify the type of grouping words, including two types of grouping words:
                        - 'cn': continuous chinese characters (e.g., 你好啊)
                        - 'en&num': continuous english characters (e.g., hello), number (e.g., 123, 1.123), or mixed of them connected by '-' (e.g., VGG-16)
                        The remaining characters in text are treated as separators between groups (e.g., space, '(', ')', etc.).
        """
        state = None
        word_content = []
        word_col_content = []
        word_list = []
        word_col_list = []
        state_list = []
        valid_col = np.where(selection == True)[0]

        for c_i, char in enumerate(text):
            if "\u4e00" <= char <= "\u9fff":
                c_state = "cn"
            elif bool(re.search("[a-zA-Z0-9]", char)):
                c_state = "en&num"
            else:
                c_state = "splitter"

            if (
                char == "."
                and state == "en&num"
                and c_i + 1 < len(text)
                and bool(re.search("[0-9]", text[c_i + 1]))
            ):  # grouping floating number
                c_state = "en&num"
            if (
                char == "-" and state == "en&num"
            ):  # grouping word with '-', such as 'state-of-the-art'
                c_state = "en&num"

            if state == None:
                state = c_state

            if state != c_state:
                if len(word_content) != 0:
                    word_list.append(word_content)
                    word_col_list.append(word_col_content)
                    state_list.append(state)
                    word_content = []
                    word_col_content = []
                state = c_state

            if state != "splitter":
                word_content.append(char)
                word_col_content.append(valid_col[c_i])

        if len(word_content) != 0:
            word_list.append(word_content)
            word_col_list.append(word_col_content)
            state_list.append(state)

        return word_list, word_col_list, state_list

    def decode(
            self,
            text_index,
            text_prob=None,
            is_remove_duplicate=False,
            return_word_box=False,
    ):
        """ convert text-index into text-label. """
        result_list = []
        batch_size = text_index.shape[0]
        blank_word = self.get_ignored_tokens()[0]
        for batch_idx in range(batch_size):
            probs = None if text_prob is None else np.array(text_prob[batch_idx])
            sequence = text_index[batch_idx]

            final_mask = sequence != blank_word
            if is_remove_duplicate:
                duplicate_mask = np.insert(sequence[1:] != sequence[:-1], 0, True)
                final_mask &= duplicate_mask

            sequence = sequence[final_mask]
            probs = None if probs is None else probs[final_mask]
            text = "".join(self.character[sequence])

            if text_prob is not None and probs is not None and len(probs) > 0:
                mean_conf = np.mean(probs)
            else:
                # 如果没有提供概率或最终结果为空，则默认置信度为1.0
                mean_conf = 1.0
            result_list.append((text, mean_conf))
        return result_list

    def get_ignored_tokens(self):
        return [0]  # for ctc blank


class CTCLabelDecode(BaseRecLabelDecode):
    """ Convert between text-label and text-index """

    def __init__(self,
                 character_dict_path=None,
                 use_space_char=False,
                 **kwargs):
        super(CTCLabelDecode, self).__init__(character_dict_path,
                                             use_space_char)

    def _decode_raw_logits(self, preds):
        """从 raw logits 直接计算 CTC argmax 和 max softmax 概率，避免完整 softmax。"""
        logits = preds["ctc_logits"]
        if torch.is_tensor(logits):
            preds_idx = logits.argmax(dim=2)
            max_logits = logits.amax(dim=2)
            preds_prob = torch.exp(max_logits - torch.logsumexp(logits, dim=2))
            return preds_prob.float().cpu().numpy(), preds_idx.cpu().numpy()

        logits = np.asarray(logits)
        preds_idx = logits.argmax(axis=2)
        max_logits = logits.max(axis=2)
        stable_logits = logits - max_logits[:, :, None]
        logsumexp = max_logits + np.log(np.exp(stable_logits).sum(axis=2))
        preds_prob = np.exp(max_logits - logsumexp).astype(np.float32)
        return preds_prob, preds_idx

    def __call__(self, preds, label=None, return_word_box=False, *args, **kwargs):
        if isinstance(preds, dict) and preds.get("ctc_use_raw_logits"):
            preds_prob, preds_idx = self._decode_raw_logits(preds)
        else:
            preds_prob, preds_idx = preds.max(axis=2)
            preds_idx = preds_idx.cpu().numpy()
            preds_prob = preds_prob.float().cpu().numpy()
        text = self.decode(
            preds_idx,
            preds_prob,
            is_remove_duplicate=True,
            return_word_box=return_word_box,
        )
        if return_word_box:
            for rec_idx, rec in enumerate(text):
                wh_ratio = kwargs["wh_ratio_list"][rec_idx]
                max_wh_ratio = kwargs["max_wh_ratio"]
                rec[2][0] = rec[2][0] * (wh_ratio / max_wh_ratio)

        if label is None:
            return text
        label = self.decode(label.cpu().numpy())
        return text, label

    def add_special_char(self, dict_character):
        dict_character = ['blank'] + dict_character
        return dict_character
