# widgets/control_panel.py
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGroupBox,
    QFormLayout,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QTabWidget,
)


class ControlPanel(QWidget):
    """
    右侧参数设置区
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(8)

        self.tab_widget = QTabWidget()

        self.tab_widget.addTab(self._build_scanbody_tab(), "扫描杆匹配")
        self.tab_widget.addTab(self._build_cuff_tab(), "袖口识别")
        self.tab_widget.addTab(self._build_design_tab(), "基台生成")

        root_layout.addWidget(self.tab_widget)

    def _build_scanbody_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox("扫描杆自动匹配参数")
        form = QFormLayout(group)

        self.match_voxel_size = QDoubleSpinBox()
        self.match_voxel_size.setRange(0.01, 5.0)
        self.match_voxel_size.setDecimals(3)
        self.match_voxel_size.setValue(0.30)

        self.match_ransac_iter = QSpinBox()
        self.match_ransac_iter.setRange(100, 100000)
        self.match_ransac_iter.setValue(4000)

        self.match_distance_thresh = QDoubleSpinBox()
        self.match_distance_thresh.setRange(0.01, 10.0)
        self.match_distance_thresh.setDecimals(3)
        self.match_distance_thresh.setValue(1.50)

        self.match_enable_refine = QCheckBox("启用精配准")
        self.match_enable_refine.setChecked(True)

        form.addRow("体素下采样尺寸", self.match_voxel_size)
        form.addRow("粗配准迭代次数", self.match_ransac_iter)
        form.addRow("对应距离阈值", self.match_distance_thresh)
        form.addRow("", self.match_enable_refine)

        layout.addWidget(group)
        layout.addStretch(1)
        return widget

    def _build_cuff_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox("袖口识别 / 边界定位参数")
        form = QFormLayout(group)

        self.cuff_patch_radius = QDoubleSpinBox()
        self.cuff_patch_radius.setRange(0.5, 20.0)
        self.cuff_patch_radius.setDecimals(2)
        self.cuff_patch_radius.setValue(5.0)

        self.cuff_boundary_bandwidth = QDoubleSpinBox()
        self.cuff_boundary_bandwidth.setRange(0.01, 5.0)
        self.cuff_boundary_bandwidth.setDecimals(3)
        self.cuff_boundary_bandwidth.setValue(0.50)

        self.cuff_use_boundary_refine = QCheckBox("启用边界后处理")
        self.cuff_use_boundary_refine.setChecked(True)

        form.addRow("局部分析半径", self.cuff_patch_radius)
        form.addRow("边界带宽参数", self.cuff_boundary_bandwidth)
        form.addRow("", self.cuff_use_boundary_refine)

        layout.addWidget(group)
        layout.addStretch(1)
        return widget

    def _build_design_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox("个性化基台形态生成参数")
        form = QFormLayout(group)

        self.design_emergence_height = QDoubleSpinBox()
        self.design_emergence_height.setRange(0.0, 10.0)
        self.design_emergence_height.setDecimals(3)
        self.design_emergence_height.setValue(1.00)

        self.design_pressure_offset = QDoubleSpinBox()
        self.design_pressure_offset.setRange(-2.0, 5.0)
        self.design_pressure_offset.setDecimals(3)
        self.design_pressure_offset.setValue(0.30)

        self.design_smooth_weight = QDoubleSpinBox()
        self.design_smooth_weight.setRange(0.0, 100.0)
        self.design_smooth_weight.setDecimals(3)
        self.design_smooth_weight.setValue(10.0)

        self.design_export_intermediate = QCheckBox("导出中间结果")
        self.design_export_intermediate.setChecked(False)

        form.addRow("穿龈高度", self.design_emergence_height)
        form.addRow("穿龈压迫量", self.design_pressure_offset)
        form.addRow("平滑约束权重", self.design_smooth_weight)
        form.addRow("", self.design_export_intermediate)

        layout.addWidget(group)
        layout.addStretch(1)
        return widget

    def get_scanbody_match_params(self):
        return {
            "voxel_size": self.match_voxel_size.value(),
            "ransac_iterations": self.match_ransac_iter.value(),
            "distance_threshold": self.match_distance_thresh.value(),
            "enable_refine": self.match_enable_refine.isChecked(),
        }

    def get_cuff_params(self):
        return {
            "patch_radius": self.cuff_patch_radius.value(),
            "boundary_bandwidth": self.cuff_boundary_bandwidth.value(),
            "use_boundary_refine": self.cuff_use_boundary_refine.isChecked(),
        }

    def get_abutment_design_params(self):
        return {
            "emergence_height": self.design_emergence_height.value(),
            "pressure_offset": self.design_pressure_offset.value(),
            "smooth_weight": self.design_smooth_weight.value(),
            "export_intermediate": self.design_export_intermediate.isChecked(),
        }