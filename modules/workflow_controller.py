import os
from pathlib import Path
from typing import Callable, Dict, Optional

import numpy as np

from modules.abutment_designer import AbutmentDesigner
from modules.cuff_segmenter import CuffSegmenter
from modules.export_manager import ExportManager
from modules.scanbody_matcher import ScanbodyMatcher
from utils.app_config import RUNTIME_OUTPUT_DIR
from utils.geometry_transform import transform_geometry_file


class DentalDesignWorkflow:
    """
    系统流程编排层（Application Service）：
    - 统一管理流程状态与模块协作
    - 将 UI 与算法模块解耦
    """

    def __init__(
        self,
        scanbody_matcher: ScanbodyMatcher,
        cuff_segmenter: CuffSegmenter,
        abutment_designer: AbutmentDesigner,
        export_manager: ExportManager,
    ):
        self.scanbody_matcher = scanbody_matcher
        self.cuff_segmenter = cuff_segmenter
        self.abutment_designer = abutment_designer
        self.export_manager = export_manager

    @staticmethod
    def create_case_data() -> Dict:
        return {
            "standard_scanbody": None,
            "standard_abutment": None,
            "roi_indices_json": None,
            "oral_scanbody_raw": None,
            "gingiva_mesh_raw": None,
            "cuff_data_raw": None,
            "oral_scanbody": None,
            "gingiva_mesh": None,
            "cuff_data": None,
            "match_result": None,
            "cuff_result": None,
            "abutment_result": None,
            "cuff_display_type": "reference_boundary",
        }

    def register_import(self, case_data: Dict, key: str, file_path: str) -> Dict:
        updates = {
            "reset_transformed_views": False,
        }

        if key in {"standard_scanbody", "standard_abutment", "roi_indices_json"}:
            case_data[key] = file_path
            return updates

        if key == "oral_scanbody":
            case_data["oral_scanbody_raw"] = file_path
            case_data["oral_scanbody"] = file_path
            case_data["match_result"] = None
            updates["reset_transformed_views"] = True
            return updates

        if key == "gingiva_mesh":
            case_data["gingiva_mesh_raw"] = file_path
            case_data["gingiva_mesh"] = file_path
            return updates

        return updates

    def load_internal_cuff(self, case_data: Dict, cuff_path: str) -> bool:
        if not os.path.exists(cuff_path):
            return False
        case_data["cuff_data_raw"] = cuff_path
        case_data["cuff_data"] = cuff_path
        return True

    def validate_before_match(self, case_data: Dict) -> Optional[str]:
        if not case_data.get("standard_scanbody") or not case_data.get("oral_scanbody_raw"):
            return "请先导入标准扫描杆模型和口扫扫描杆模型。"
        return None

    def run_scanbody_matching(self, case_data: Dict, params: Dict, log_callback: Callable[[str], None]) -> Dict:
        result = self.scanbody_matcher.run(
            standard_scanbody_path=case_data["standard_scanbody"],
            oral_scanbody_path=case_data["oral_scanbody_raw"],
            params=params,
            log_callback=log_callback,
        )
        case_data["match_result"] = result

        transformed_outputs = {}
        if result.get("status") != "success":
            return {"result": result, "transformed_outputs": transformed_outputs}

        inverse_transformation = result.get("output", {}).get("inverse_transformation")
        if inverse_transformation is None:
            return {"result": result, "transformed_outputs": transformed_outputs}

        t_inv = np.asarray(inverse_transformation, dtype=float)
        transformed_outputs = self._transform_related_geometries(case_data=case_data, t_inv=t_inv)
        return {"result": result, "transformed_outputs": transformed_outputs}

    def _transform_related_geometries(self, case_data: Dict, t_inv: np.ndarray) -> Dict:
        outputs: Dict[str, str] = {}

        if case_data.get("oral_scanbody_raw"):
            oral_out = self._runtime_output_path(
                "oral_scanbody_in_standard",
                case_data["oral_scanbody_raw"],
                default_ext=".ply",
            )
            oral_out = transform_geometry_file(case_data["oral_scanbody_raw"], oral_out, t_inv)
            case_data["oral_scanbody"] = oral_out
            outputs["oral_scanbody_in_standard"] = oral_out

        if case_data.get("gingiva_mesh_raw"):
            gingiva_out = self._runtime_output_path(
                "gingiva_mesh_in_standard",
                case_data["gingiva_mesh_raw"],
                default_ext=".ply",
            )
            gingiva_out = transform_geometry_file(case_data["gingiva_mesh_raw"], gingiva_out, t_inv)
            case_data["gingiva_mesh"] = gingiva_out
            outputs["gingiva_mesh_in_standard"] = gingiva_out

        if case_data.get("cuff_data_raw"):
            cuff_out = self._runtime_output_path(
                "cuff_data_in_standard",
                case_data["cuff_data_raw"],
                default_ext=".ply",
            )
            cuff_out = transform_geometry_file(case_data["cuff_data_raw"], cuff_out, t_inv)
            case_data["cuff_data"] = cuff_out
            outputs["cuff_data_in_standard"] = cuff_out

        return outputs

    @staticmethod
    def _runtime_output_path(prefix: str, source_path: str, default_ext: str) -> str:
        ext = Path(source_path).suffix or default_ext
        return str(RUNTIME_OUTPUT_DIR / f"{prefix}{ext}")

    def validate_before_cuff(self, case_data: Dict) -> Optional[str]:
        if not case_data.get("gingiva_mesh"):
            return "请先导入患者牙齿模型。"
        if not case_data.get("cuff_data"):
            return "程序内部袖口模型未加载成功。"
        if not case_data.get("match_result"):
            return "请先执行扫描杆匹配。"
        return None

    def run_cuff_segmentation(self, case_data: Dict, params: Dict, log_callback: Callable[[str], None]) -> Dict:
        result = self.cuff_segmenter.run(
            gingiva_mesh_path=case_data["gingiva_mesh"],
            cuff_data_path=case_data["cuff_data"],
            params=params,
            log_callback=log_callback,
        )
        case_data["cuff_result"] = result
        return result

    def validate_before_design(self, case_data: Dict) -> Optional[str]:
        if not case_data.get("standard_abutment"):
            return "请先导入标准基台模型。"
        if not case_data.get("roi_indices_json"):
            return "请先导入 ROI 索引文件。"
        if not case_data.get("cuff_result") or case_data["cuff_result"].get("status") != "success":
            return "请先完成袖口识别并生成参考边界。"
        return None

    def run_abutment_design(self, case_data: Dict, params: Dict, log_callback: Callable[[str], None]) -> Dict:
        result = self.abutment_designer.run(
            standard_abutment_path=case_data["standard_abutment"],
            roi_indices_json_path=case_data["roi_indices_json"],
            match_result=case_data["match_result"],
            cuff_result=case_data["cuff_result"],
            params=params,
            gingiva_mesh_path=case_data.get("gingiva_mesh"),
            log_callback=log_callback,
        )
        case_data["abutment_result"] = result
        return result

    def export_results(self, case_data: Dict, export_root_dir: str) -> Dict:
        return self.export_manager.export_case_results(case_data=case_data, export_root_dir=export_root_dir)
