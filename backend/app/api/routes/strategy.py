# app/api/routes/strategy.py
from fastapi import APIRouter, BackgroundTasks, Query
from app.services.data_preprocessing import preprocess_all_data
from app.services.ws_manager import ws_manager
from app.schemas.common import ApiResponse, BusinessCode
from app.utils import run_with_ws_notify
from app.services.weekly_aggregator import create_weekly_dataset
from app.services.train_test_split import split_train_test
from app.services.rolling_ols import run_rolling_ols
from app.services.backtest import run_backtest
from app.services.realtime import run_realtime

router = APIRouter(prefix="/strategy", tags=["策略流程"])


# response_model用于自动检测输出、生成API文档、自动序列化json
@router.post("/preprocess", response_model=ApiResponse)
async def run_preprocessing(background_tasks: BackgroundTasks):
    """触发数据预处理任务"""

    background_tasks.add_task(
        run_with_ws_notify,
        "数据预处理",
        preprocess_all_data,
        event_type = "experiment_completed"
    )
    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="数据预处理任务已启动，请查看日志确认进度",
        data=None
    )


@router.post("/weekly-aggregate", response_model=ApiResponse)
async def run_weekly_aggregate(background_tasks: BackgroundTasks, exp_id: int = None):
    """触发周频数据聚合任务"""
    background_tasks.add_task(
        run_with_ws_notify,
        "数据周频聚合",
        create_weekly_dataset,
        event_type = "experiment_completed",
        exp_id=exp_id,
    )

    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="周频聚合任务已启动，请稍后查看日志",
        data=None
    )


@router.post("/split-data", response_model=ApiResponse)
async def run_split_data(
    background_tasks: BackgroundTasks,
    exp_id: int = Query(..., description="实验ID（必填）"),
    split_ratio: float = 0.7,
):
    """执行训练/测试集划分"""
    background_tasks.add_task(
        run_with_ws_notify,
        "训练/测试集划分",
        split_train_test,
        event_type = "experiment_completed",
        exp_id=exp_id,
        split_ratio=split_ratio,
    )
    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="训练/测试集划分已启动",
        data={"exp_id": exp_id}
    )


@router.post("/train-ols", response_model=ApiResponse)
async def trigger_train_ols(
    background_tasks: BackgroundTasks,
    exp_id: int = Query(..., description="实验ID（必填）"),
    window: int = 252,
    zscore_window: int = 52,
    buy_threshold: float = 0.5,
    sell_threshold: float = -0.5,
    factor_cols: list = None,
    y_col: str = None
):
    """执行滚动 OLS 训练与信号生成"""
    background_tasks.add_task(
        run_with_ws_notify,
        "滚动OLS训练",
        run_rolling_ols,
        event_type = "experiment_completed",
        window = window,
        zscore_window = zscore_window,
        buy_threshold = buy_threshold,
        sell_threshold = sell_threshold,
        factor_cols = factor_cols,
        y_col = y_col,
        exp_id = exp_id
    )
    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="滚动训练任务已启动",
        data=None
    )

@router.post("/backtest", response_model=ApiResponse)
async def trigger_backtest(
    background_tasks: BackgroundTasks,
    exp_id: int = Query(..., description="实验ID（必填）"),
):
    """执行回测模拟"""
    background_tasks.add_task(
        run_with_ws_notify,
        "回测模拟",
        run_backtest,
        event_type = "experiment_completed",
        exp_id = exp_id
    )
    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="回测任务已启动",
        data=None
    )

@router.post("/realtime", response_model=ApiResponse)
async def trigger_realtime(
    background_tasks: BackgroundTasks,
    exp_id: int = Query(..., description="实验ID（必填）"),
    initial_cash: float = 10000.0,
    min_hold_days: int = 7
):
    """执行实盘模拟"""
    background_tasks.add_task(
        run_with_ws_notify,
        "实盘模拟",
        run_realtime,
        event_type = "experiment_completed",
        exp_id = exp_id,
        initial_cash = initial_cash,
        min_hold_days = min_hold_days
    )
    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="实盘模拟已启动",
        data=None
    )