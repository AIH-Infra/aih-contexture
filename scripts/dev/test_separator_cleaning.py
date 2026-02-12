"""
测试页面分隔符清理功能

演示如何处理 VLM 输出中自带的分隔符，避免嵌套。
"""

def test_clean_page_separators():
    """测试分隔符清理功能"""
    import re

    def clean_page_separators(pages):
        """清理页面中的多余分隔符"""
        cleaned_pages = []
        separator_pattern = r'^\s*---+\s*$'

        for page in pages:
            lines = page.split('\n')

            # 移除开头的分隔符
            while lines and re.match(separator_pattern, lines[0]):
                lines.pop(0)

            # 移除结尾的分隔符
            while lines and re.match(separator_pattern, lines[-1]):
                lines.pop()

            cleaned_page = '\n'.join(lines).strip()
            cleaned_pages.append(cleaned_page)

        return cleaned_pages

    # 测试用例 1: 页面末尾有分隔符
    pages_1 = [
        "# 第一页\n\n内容...\n\n---",
        "# 第二页\n\n内容..."
    ]

    print("=" * 60)
    print("测试用例 1: 页面末尾有分隔符")
    print("=" * 60)
    print("\n原始页面:")
    for i, page in enumerate(pages_1):
        print(f"\n页面 {i}:")
        print(repr(page))

    cleaned_1 = clean_page_separators(pages_1)
    print("\n清理后:")
    for i, page in enumerate(cleaned_1):
        print(f"\n页面 {i}:")
        print(repr(page))

    # 拼接
    result_1 = "\n\n---\n\n".join(cleaned_1)
    print("\n拼接结果:")
    print(result_1)

    # 测试用例 2: 页面开头和结尾都有分隔符
    pages_2 = [
        "---\n\n# 第一页\n\n内容...\n\n---",
        "---\n\n# 第二页\n\n内容...\n\n---"
    ]

    print("\n" + "=" * 60)
    print("测试用例 2: 页面开头和结尾都有分隔符")
    print("=" * 60)
    print("\n原始页面:")
    for i, page in enumerate(pages_2):
        print(f"\n页面 {i}:")
        print(repr(page))

    cleaned_2 = clean_page_separators(pages_2)
    print("\n清理后:")
    for i, page in enumerate(cleaned_2):
        print(f"\n页面 {i}:")
        print(repr(page))

    # 拼接
    result_2 = "\n\n---\n\n".join(cleaned_2)
    print("\n拼接结果:")
    print(result_2)

    # 测试用例 3: 混合情况
    pages_3 = [
        "# 第一页\n\n内容...",  # 无分隔符
        "---\n\n# 第二页\n\n内容...\n\n---",  # 两端都有
        "# 第三页\n\n内容...\n\n---",  # 仅末尾
        "---\n\n# 第四页\n\n内容..."  # 仅开头
    ]

    print("\n" + "=" * 60)
    print("测试用例 3: 混合情况")
    print("=" * 60)
    print("\n原始页面:")
    for i, page in enumerate(pages_3):
        print(f"\n页面 {i}:")
        print(repr(page))

    cleaned_3 = clean_page_separators(pages_3)
    print("\n清理后:")
    for i, page in enumerate(cleaned_3):
        print(f"\n页面 {i}:")
        print(repr(page))

    # 拼接
    result_3 = "\n\n---\n\n".join(cleaned_3)
    print("\n拼接结果:")
    print(result_3)

    # 测试用例 4: 多个连续分隔符
    pages_4 = [
        "# 第一页\n\n---\n---\n---",
        "---\n---\n# 第二页"
    ]

    print("\n" + "=" * 60)
    print("测试用例 4: 多个连续分隔符")
    print("=" * 60)
    print("\n原始页面:")
    for i, page in enumerate(pages_4):
        print(f"\n页面 {i}:")
        print(repr(page))

    cleaned_4 = clean_page_separators(pages_4)
    print("\n清理后:")
    for i, page in enumerate(cleaned_4):
        print(f"\n页面 {i}:")
        print(repr(page))

    # 拼接
    result_4 = "\n\n---\n\n".join(cleaned_4)
    print("\n拼接结果:")
    print(result_4)

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    test_clean_page_separators()
