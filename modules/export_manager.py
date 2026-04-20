# modules/export_manager.py
import json
import os
import shutil
from datetime import datetime
from typing import Dict, List, Optional


class ExportManager:
    """
    结果导出模块

    导出策略：
    1. 按模块结果分别导出到子目录
       - scanbody_match/
       - cuff_result/
       - abutment_result/
    2. 复制真实输出文件
    3. 同时生成 export_manifest.json 记录导出内容
    """

    def __init__(self):
        self.name = "ExportManager"

    # ============================================================
    # 对外主接口
    # ============================================================
    def export_case_results(self, case_data: dict, export_root_dir: str) -> Dict:
        export_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = os.path.join(export_root_dir, "dental_abutment_export_{}".format(export_time))
        os.makedirs(export_dir, exist_ok=True)

        exported_files: List[str] = []
        exported_modules: List[str] = []
        warnings: List[str] = []

        # 1. 扫描杆匹配结果
        match_result = case_data.get("match_result")
        if self._is_success_result(match_result):
            match_dir = os.path.join(export_dir, "scanbody_match")
            os.makedirs(match_dir, exist_ok=True)

            match_info_path = os.path.join(match_dir, "match_result.json")
            self._write_json(match_info_path, match_result)
            exported_files.append(match_info_path)

            aligned_model_path = match_result.get("output", {}).get("aligned_model_path")
            copied = self._copy_if_exists(
                aligned_model_path,
                os.path.join(match_dir, self._basename_or_default(aligned_model_path, "aligned_model.ply"))
            )
            if copied:
                exported_files.append(copied)

            exported_modules.append("scanbody_match")
        else:
            warnings.append("扫描杆匹配结果不存在或未成功生成。")

        # 2. 袖口识别结果
        cuff_result = case_data.get("cuff_result")
        if self._is_success_result(cuff_result):
            cuff_dir = os.path.join(export_dir, "cuff_result")
            os.makedirs(cuff_dir, exist_ok=True)

            cuff_info_path = os.path.join(cuff_dir, "cuff_result.json")
            self._write_json(cuff_info_path, cuff_result)
            exported_files.append(cuff_info_path)

            cuff_output = cuff_result.get("output", {})

            cuff_file_keys = [
                "boundary_points_path",
                "boundary_points_txt_path",
                "reference_curve_path",
                "reference_curve_txt_path",
                "boundary_display_path",
                "boundary_display_txt_path",
                "reference_display_path",
                "reference_display_txt_path",
                "segmentation_mask_path",
            ]

            for key in cuff_file_keys:
                src = cuff_output.get(key)
                copied = self._copy_if_exists(
                    src,
                    os.path.join(cuff_dir, self._basename_or_default(src, key))
                )
                if copied:
                    exported_files.append(copied)

            exported_modules.append("cuff_result")
        else:
            warnings.append("袖口识别结果不存在或未成功生成。")

        # 3. 基台形变结果
        abutment_result = case_data.get("abutment_result")
        if self._is_success_result(abutment_result):
            abutment_dir = os.path.join(export_dir, "abutment_result")
            os.makedirs(abutment_dir, exist_ok=True)

            abutment_info_path = os.path.join(abutment_dir, "abutment_result.json")
            self._write_json(abutment_info_path, abutment_result)
            exported_files.append(abutment_info_path)

            abutment_output = abutment_result.get("output", {})
            abutment_file_keys = [
                "output_model_path",
                "top_target_vertices_path",
                "bottom_target_vertices_path",
            ]

            for key in abutment_file_keys:
                src = abutment_output.get(key)
                copied = self._copy_if_exists(
                    src,
                    os.path.join(abutment_dir, self._basename_or_default(src, key))
                )
                if copied:
                    exported_files.append(copied)

            exported_modules.append("abutment_result")
        else:
            warnings.append("基台形变结果不存在或未成功生成。")

        # 4. 导出总清单
        manifest = {
            "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "export_dir": export_dir,
            "exported_modules": exported_modules,
            "exported_file_count": len(exported_files),
            "exported_files": exported_files,
            "warnings": warnings,
        }

        manifest_path = os.path.join(export_dir, "export_manifest.json")
        self._write_json(manifest_path, manifest)

        return {
            "success": True,
            "export_dir": export_dir,
            "manifest_path": manifest_path,
            "exported_modules": exported_modules,
            "exported_file_count": len(exported_files),
            "warnings": warnings,
        }

    # ============================================================
    # 兼容旧接口：单模型导出
    # ============================================================
    def export_model(self, result: dict, save_path: str) -> bool:
        """
        保留兼容旧接口。
        优先导出 abutment_result 的 output_model_path，
        若没有，则尝试 aligned_model_path。
        """
        try:
            if not isinstance(result, dict):
                return False

            output = result.get("output", {})
            if not isinstance(output, dict):
                return False

            candidate_keys = [
                "output_model_path",
                "aligned_model_path",
                "reference_curve_path",
                "boundary_display_path",
            ]

            for key in candidate_keys:
                src = output.get(key)
                if src and os.path.exists(src):
                    shutil.copyfile(src, save_path)
                    return True

            return False
        except Exception:
            return False

    # ============================================================
    # 内部工具
    # ============================================================
    def _is_success_result(self, result: Optional[dict]) -> bool:
        return isinstance(result, dict) and result.get("status") == "success"

    def _write_json(self, path: str, data: dict):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _copy_if_exists(self, src: Optional[str], dst: str) -> Optional[str]:
        if not src:
            return None
        if not os.path.exists(src):
            return None

        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        return dst

    def _basename_or_default(self, path: Optional[str], default_name: str) -> str:
        if not path:
            return default_name
        return os.path.basename(path)