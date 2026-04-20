# widgets/data_panel.py
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGroupBox,
    QPushButton,
    QLabel,
    QGridLayout,
    QFrame,
    QCheckBox,
    QSizePolicy,
    QComboBox,
)


class DataPanel(QWidget):
    """
    左侧面板：
    1. 数据导入区
    2. 功能流程区
    3. 模型显示控制区
    """

    import_standard_scanbody_requested = Signal()
    import_standard_abutment_requested = Signal()
    import_roi_json_requested = Signal()
    import_oral_scanbody_requested = Signal()
    import_gingiva_requested = Signal()

    run_matching_requested = Signal()
    run_cuff_requested = Signal()
    run_design_requested = Signal()

    export_requested = Signal()
    cuff_display_type_changed = Signal(str)
    toggle_visibility_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_labels = {}
        self.visibility_checkboxes = {}
        self._init_ui()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(8)

        root_layout.addWidget(self._build_data_group())
        root_layout.addWidget(self._build_process_group())
        root_layout.addWidget(self._build_visibility_group())
        root_layout.addStretch(1)

    def _build_data_group(self):
        group = QGroupBox("病例 / 数据管理")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        layout.addWidget(self._create_import_row(
            title="标准扫描杆模型",
            signal_name="import_standard_scanbody_requested",
            key="standard_scanbody"
        ))
        layout.addWidget(self._create_import_row(
            title="标准基台模型",
            signal_name="import_standard_abutment_requested",
            key="standard_abutment"
        ))
        layout.addWidget(self._create_import_row(
            title="ROI 索引文件",
            signal_name="import_roi_json_requested",
            key="roi_indices_json"
        ))
        layout.addWidget(self._create_import_row(
            title="口扫扫描杆模型",
            signal_name="import_oral_scanbody_requested",
            key="oral_scanbody"
        ))
        layout.addWidget(self._create_import_row(
            title="完整牙龈模型",
            signal_name="import_gingiva_requested",
            key="gingiva_mesh"
        ))

        return group

    def _create_import_row(self, title, signal_name, key):
        container = QFrame()
        container.setFrameShape(QFrame.StyledPanel)

        layout = QGridLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(4)

        title_label = QLabel(title)
        title_label.setMinimumWidth(90)

        status_label = QLabel("未导入")
        status_label.setStyleSheet("color: gray;")
        status_label.setWordWrap(True)
        status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        import_button = QPushButton("导入")
        signal_obj = getattr(self, signal_name)
        import_button.clicked.connect(signal_obj.emit)

        layout.addWidget(title_label, 0, 0)
        layout.addWidget(import_button, 0, 1)
        layout.addWidget(status_label, 1, 0, 1, 2)

        self.file_labels[key] = status_label
        return container

    def _build_process_group(self):
        group = QGroupBox("功能流程")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        btn_match = QPushButton("1. 执行扫描杆匹配")
        btn_cuff = QPushButton("2. 执行袖口识别 / 边界定位")
        btn_design = QPushButton("3. 执行基台形态生成")
        btn_export = QPushButton("4. 导出结果")

        btn_match.clicked.connect(self.run_matching_requested.emit)
        btn_cuff.clicked.connect(self.run_cuff_requested.emit)
        btn_design.clicked.connect(self.run_design_requested.emit)
        btn_export.clicked.connect(self.export_requested.emit)

        layout.addWidget(btn_match)
        layout.addWidget(btn_cuff)
        layout.addWidget(btn_design)
        layout.addWidget(btn_export)

        return group

    def _build_visibility_group(self):
        group = QGroupBox("显示控制")
        layout = QVBoxLayout(group)
        layout.setSpacing(6)

        items = [
            ("standard_scanbody", "显示标准扫描杆"),
            ("standard_abutment", "显示标准基台"),
            ("oral_scanbody", "显示患者扫描杆"),
            ("gingiva_mesh", "显示患者牙齿模型"),

            ("oral_scanbody_in_standard", "显示变换后患者扫描杆"),
            ("gingiva_mesh_in_standard", "显示变换后患者牙齿模型"),

            ("match_result", "显示匹配结果"),
            ("cuff_result", "显示袖口结果"),
            ("abutment_result", "显示基台结果"),
        ]

        for key, text in items:
            checkbox = QCheckBox(text)
            checkbox.setChecked(True)
            checkbox.clicked.connect(
                lambda checked=False, model_key=key: self.toggle_visibility_requested.emit(model_key)
            )
            layout.addWidget(checkbox)
            self.visibility_checkboxes[key] = checkbox

        # 新增：袖口边界显示类型切换
        mode_label = QLabel("袖口边界显示")
        self.cuff_display_type_combo = QComboBox()
        self.cuff_display_type_combo.addItem("参考边界", "reference_boundary")
        self.cuff_display_type_combo.addItem("原始边界", "raw_boundary")
        self.cuff_display_type_combo.setCurrentIndex(0)
        self.cuff_display_type_combo.currentIndexChanged.connect(self._emit_cuff_display_type_changed)

        layout.addSpacing(8)
        layout.addWidget(mode_label)
        layout.addWidget(self.cuff_display_type_combo)

        return group

    def _emit_cuff_display_type_changed(self):
        if hasattr(self, "cuff_display_type_combo"):
            self.cuff_display_type_changed.emit(self.cuff_display_type_combo.currentData())

    def get_cuff_display_type(self) -> str:
        if hasattr(self, "cuff_display_type_combo"):
            return self.cuff_display_type_combo.currentData()
        return "reference_boundary"

    def set_cuff_display_type(self, value: str):
        if not hasattr(self, "cuff_display_type_combo"):
            return

        index = self.cuff_display_type_combo.findData(value)
        if index < 0:
            return

        old = self.cuff_display_type_combo.blockSignals(True)
        self.cuff_display_type_combo.setCurrentIndex(index)
        self.cuff_display_type_combo.blockSignals(old)

    def update_file_status(self, key: str, file_path: str):
        """
        更新导入状态显示
        """
        if key not in self.file_labels:
            return

        path = Path(file_path)
        text = "已导入：{}".format(path.name)
        self.file_labels[key].setText(text)
        self.file_labels[key].setStyleSheet("color: #1f6f43;")

    def set_file_unloaded(self, key: str):
        """
        可选接口：后续支持移除模型时使用
        """
        if key not in self.file_labels:
            return

        self.file_labels[key].setText("未导入")
        self.file_labels[key].setStyleSheet("color: gray;")

    def set_visibility_state(self, key: str, visible: bool):
        """
        由主窗口/程序主动同步复选框状态。
        不触发用户点击逻辑，只更新界面勾选状态。
        """
        checkbox = self.visibility_checkboxes.get(key)
        if checkbox is None:
            return

        old = checkbox.blockSignals(True)
        checkbox.setChecked(visible)
        checkbox.blockSignals(old)

    def set_checkbox_enabled(self, key: str, enabled: bool):
        checkbox = self.visibility_checkboxes.get(key)
        if checkbox is None:
            return
        checkbox.setEnabled(enabled)