"""
Test script for CustomIDInjector functionality
"""

from aih_contexture.formatters import CustomIDInjector, PageAnchorFormatter, PageAnchorPlugin

def test_custom_id_injector():
    print("=" * 60)
    print("Testing CustomIDInjector")
    print("=" * 60)

    # Test 1: None source
    print("\n1. Testing 'none' source:")
    injector = CustomIDInjector(source_type="none")
    print(f"   Page 0: {injector.get_custom_id(0)}")
    print(f"   Page 1: {injector.get_custom_id(1)}")

    # Test 2: List source
    print("\n2. Testing 'list' source:")
    injector = CustomIDInjector(source_type="list", source_data=["sc001", "sc002", "sc003"])
    print(f"   Page 0: {injector.get_custom_id(0)}")
    print(f"   Page 1: {injector.get_custom_id(1)}")
    print(f"   Page 2: {injector.get_custom_id(2)}")
    print(f"   Page 3 (out of range): {injector.get_custom_id(3)}")

    # Test 3: Auto source
    print("\n3. Testing 'auto' source:")
    injector = CustomIDInjector(
        source_type="auto",
        source_data={"prefix": "sc", "start": 1, "digits": 3}
    )
    print(f"   Page 0: {injector.get_custom_id(0)}")
    print(f"   Page 1: {injector.get_custom_id(1)}")
    print(f"   Page 10: {injector.get_custom_id(10)}")

    # Test 4: PageAnchorPlugin with CustomIDInjector
    print("\n4. Testing PageAnchorPlugin with CustomIDInjector:")
    formatter = PageAnchorFormatter(wrapper="{{{}}}")
    injector = CustomIDInjector(
        source_type="auto",
        source_data={"prefix": "sc", "start": 1, "digits": 3}
    )
    plugin = PageAnchorPlugin(
        formatter=formatter,
        enabled=True,
        position="before",
        separator="\n\n",
        custom_id_injector=injector
    )

    content = "This is page content."
    result = plugin.wrap_page_content(0, content)
    print(f"   Result:\n{result}")

    # Test 5: PageAnchorPlugin with printed_page_id (priority test)
    print("\n5. Testing priority (printed_page_id > custom_id):")
    result = plugin.wrap_page_content(0, content, printed_page_id="XII")
    print(f"   Result:\n{result}")

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)

if __name__ == "__main__":
    test_custom_id_injector()
