# modules/export_manager.py
import os
import shutil


class ExportManager:
    """
    结果导出模块

    优先逻辑：
    1. 如果 result 中已有真实 output_model_path，则直接复制
    2. 否则导出一个占位三角网格文件
    """

    def __init__(self):
        self.name = "ExportManager"

    def export_model(self, result: dict, save_path: str) -> bool:
        try:
            real_output_path = self._get_real_output_path(result)

            if real_output_path and os.path.exists(real_output_path):
                shutil.copyfile(real_output_path, save_path)
                return True

            ext = os.path.splitext(save_path)[1].lower()
            if ext == ".ply":
                self._write_placeholder_ply(save_path)
            elif ext == ".obj":
                self._write_placeholder_obj(save_path)
            elif ext == ".stl":
                self._write_placeholder_stl(save_path)
            else:
                # 默认仍写一个简单文本占位
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write("Placeholder export result.\n")
            return True
        except Exception:
            return False

    def _get_real_output_path(self, result: dict):
        if not isinstance(result, dict):
            return None

        output = result.get("output", {})
        if not isinstance(output, dict):
            return None

        return output.get("output_model_path", None)

    def _write_placeholder_ply(self, save_path: str):
        content = """ply
format ascii 1.0
comment placeholder abutment result
element vertex 4
property float x
property float y
property float z
element face 4
property list uchar int vertex_indices
end_header
0 0 0
1 0 0
0 1 0
0 0 1
3 0 1 2
3 0 1 3
3 0 2 3
3 1 2 3
"""
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(content)

    def _write_placeholder_obj(self, save_path: str):
        content = """# placeholder abutment result
v 0 0 0
v 1 0 0
v 0 1 0
v 0 0 1
f 1 2 3
f 1 2 4
f 1 3 4
f 2 3 4
"""
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(content)

    def _write_placeholder_stl(self, save_path: str):
        content = """solid placeholder
facet normal 0 0 1
outer loop
vertex 0 0 0
vertex 1 0 0
vertex 0 1 0
endloop
endfacet
facet normal 0 1 0
outer loop
vertex 0 0 0
vertex 1 0 0
vertex 0 0 1
endloop
endfacet
facet normal 1 0 0
outer loop
vertex 0 0 0
vertex 0 1 0
vertex 0 0 1
endloop
endfacet
facet normal 1 1 1
outer loop
vertex 1 0 0
vertex 0 1 0
vertex 0 0 1
endloop
endfacet
endsolid placeholder
"""
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(content)