"""AIH-Contexture 包根。

此文件必须存在：缺少它时 ``aih_contexture`` 会成为 PEP 420 命名空间包，
Python 会把 sys.path 上所有同名目录合并为一个包——当开发目录与部署目录
同时出现在 sys.path 上时，会静默混装两套代码（曾导致极难排查的事故）。
本项目的每一份副本（dev / 各部署目录）都必须保留此文件。
"""

__version__ = "0.9.0"
