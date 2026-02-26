# -*- coding: utf-8 -*-
"""共通データモデル（dataclass）"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class GameConfig:
    """コンツーリングゲームの設定"""
    enabled: bool = False
    ct_path: Optional[str] = None
    roi_names: Optional[List[str]] = None
    time_limit_sec: int = 0
    out_dir: Optional[str] = None
    participant: Optional[str] = None
    team: Optional[str] = None
    session_id: Optional[str] = None
    gt_label_path: Optional[str] = None
    tutorial_mode: bool = False
    gt_edit_mode: bool = False


@dataclass
class ScoreResult:
    """ROI単位のスコア結果"""
    roi_name: str
    dice_score: float
    axial_smoothness: float
    volume_smoothness: float
    total_score: float
    details: Dict


@dataclass
class GameResult:
    """ゲーム全体の結果"""
    participant: str
    team: str
    session_id: str
    case: str
    roi_order: List[str]
    time_limit_sec: int
    elapsed_sec: int
    scores: List[ScoreResult]
    overall_score: float


@dataclass
class ParticipantResult:
    """参加者の結果データ（複数モード/複数ファイル対応）"""
    participant: str
    team: str
    session_id: str
    case: str
    json_paths: List[str]
    nii_paths: List[Optional[str]]
    roi_order: List[str]
    labels: List[Dict]


@dataclass
class GroupData:
    """グループ（班）の全データ"""
    team: str
    participants: List[ParticipantResult]
    ct_path: Optional[str]
    gt_path: Optional[str]
    roi_names: List[str]
    gt_json_path: Optional[str] = None
    gt_labels: List[Dict] = field(default_factory=list)
    case_gt_labels: Dict[str, List[Dict]] = field(default_factory=dict)  # ケースごとのGT labels
    case_gt_paths: Dict[str, str] = field(default_factory=dict)  # ケースごとのGT NIfTI paths
