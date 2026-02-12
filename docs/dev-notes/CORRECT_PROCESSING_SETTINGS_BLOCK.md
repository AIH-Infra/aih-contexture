# 处理设置块的正确代码 (第1371-1447行)

```python
            # ==================== 6. 处理设置 ====================
            st.subheader("⚡ 处理设置")

            # 批处理模式选择
            batch_mode = st.radio(
                "处理模式",
                options=["自动", "单批处理", "分批处理"],
                index=0,
                horizontal=True,
                help="自动：根据页数自动决定；单批：一次性处理所有页面；分批：分批处理大文档"
            )

            # 根据选择显示相关设置
            if batch_mode == "分批处理" or batch_mode == "自动":
                st.info("💡 分批处理说明：分批是为了本地部署后端时降低性能压力，批次间冷却是为了改善散热")

                col_a, col_b = st.columns(2)
                with col_a:
                    batch_threshold = st.number_input(
                        "分批阈值（页）",
                        min_value=10,
                        max_value=2000,
                        value=50,
                        help="超过此页数自动分批（仅自动模式生效）",
                    )
                    pages_per_batch = st.number_input(
                        "每批页数",
                        min_value=5,
                        max_value=1000,
                        value=25,
                        help="每批处理的页面数量"
                    )
                with col_b:
                    cooling_seconds = st.number_input(
                        "批次间冷却（秒）",
                        min_value=0,
                        max_value=30,
                        value=5,
                        help="每批处理后等待时间，用于显存回收和散热",
                    )
            else:
                # 单批处理模式，使用默认值
                batch_threshold = 50
                pages_per_batch = 25
                cooling_seconds = 0

            # 映射到原有的 process_mode 变量
            if batch_mode == "自动":
                process_mode = "自动"
            elif batch_mode == "单批处理":
                process_mode = "强制单批"
            else:
                process_mode = "强制分批"

            # 页码范围选择
            use_page_range = st.checkbox("指定页码范围", value=False)
            if use_page_range:
                col_start, col_end = st.columns(2)
                with col_start:
                    start_page_1based = st.number_input("起始页", min_value=1, value=1)
                with col_end:
                    end_page_1based = st.number_input("结束页", min_value=1, value=10)
            else:
                start_page_1based = None
                end_page_1based = None

            st.divider()

            # ==================== 5. 高级选项（折叠） ====================
            with st.expander("🔧 高级选项", expanded=False):
                use_fp16 = st.checkbox(
                "使用 FP16",
                value=os.environ.get("USE_FP16", "false").lower() == "true",
                help="半精度推理，减少显存占用",
                )

            st.divider()
```

请将这段代码替换到streamlit_app.py的第1371-1447行。
