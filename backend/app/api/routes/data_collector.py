import os, glob
import pandas as pd
from fastapi import APIRouter, BackgroundTasks
from app.services.data_collector import (
    update_all_data,
    update_huaan_nav,
    update_spot_hist_sge,
    update_518880_daily,
    update_gold_goldAPI_spot,
    update_dxy_yfinance,
    update_dgs10,
    update_usdcny,
    update_brent,
    update_spdr_gold_holdings,
)
from app.services.wallstreetcn_kline_utils import update_kline_to_latest
from app.core.config import settings
from app.utils import get_original_data_dir
from app.schemas.common import ApiResponse, BusinessCode
from app.utils.task_utils import run_with_ws_notify
router = APIRouter(prefix="/data-collector", tags=["数据采集"])

# 后台执行流程
# 客户端发起 POST /data-collector/update
#   ↓
# FastAPI 调用 trigger_update(background_tasks)
#   ↓
# background_tasks.add_task(update_all_data)   ← 只是注册，不立即执行
#   ↓
# 立即返回 {"message": "数据更新任务已启动..."}
#   ↓ (响应已发送)
# 后台开始执行 update_all_data()
#   ↓
# 控制台/日志可以看到更新进度
@router.post("/update", response_model=ApiResponse)
async def trigger_update(background_tasks: BackgroundTasks):
    """
    触发一次全量数据更新（异步后台执行，避免前端长时间等待）
    """
    background_tasks.add_task(
        run_with_ws_notify,
        "全量数据更新",
        update_all_data
    )
    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="数据更新任务已启动，请稍后查看日志",
        data=None
    )

# ------------------------------------------------------------
# 单个数据源更新接口
# ------------------------------------------------------------
@router.post("/update/spot", response_model=ApiResponse )
async def trigger_update_spot(background_tasks: BackgroundTasks):
    """更新 Au99.99 现货日线"""
    filename = str(get_original_data_dir() / "spot_hist_sge.csv")
    background_tasks.add_task(
        run_with_ws_notify,
        "Au99.99 更新",
        update_spot_hist_sge,
        event_type = "task_completed",
        filename = filename
    )

    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="Au99.99 现货更新已启动",
        data=None
    )

@router.post("/update/nav", response_model=ApiResponse)
async def trigger_update_nav(background_tasks: BackgroundTasks):
    """更新 000217 联接基金净值"""
    filename = str(get_original_data_dir() / "huaan_gold_etf_c_hist_df.csv")
    background_tasks.add_task(
        run_with_ws_notify,
        "000217 联接基金净值更新",
        update_huaan_nav,
        filename
    )
    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="000217 净值更新已启动",
        data=None
    )

@router.post("/update/etf", response_model=ApiResponse)
async def trigger_update_etf(background_tasks: BackgroundTasks):
    """更新 518880 日K线（TickFlow）"""
    filename = str(get_original_data_dir() / "fund_etf518880_tickflow.csv")
    background_tasks.add_task(
        run_with_ws_notify,
        "518880 日K线更新",
        update_518880_daily,
        filename
    )
    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="518880 行情更新已启动",
        data=None
    )

@router.post("/update/goldapi", response_model=ApiResponse)
async def trigger_update_goldapi(background_tasks: BackgroundTasks):
    """更新国际金价（GoldAPI）"""
    filename = str(get_original_data_dir() / "gold_goldAPI_spot_hist_df.csv")
    background_tasks.add_task(
        run_with_ws_notify,
        "国际金价（GoldAPI）更新",
        update_gold_goldAPI_spot,
        filename
    )
    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="国际金价更新已启动",
        data=None
    )

@router.post("/update/dxy", response_model=ApiResponse)
async def trigger_update_dxy(background_tasks: BackgroundTasks):
    """更新美元指数"""
    filename = str(get_original_data_dir() / "dxy_yfinance_hist_df.csv")
    background_tasks.add_task(
        run_with_ws_notify,
        "美元指数更新",
        update_dxy_yfinance,
        filename
    )
    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="美元指数更新已启动",
        data=None
    )

@router.post("/update/dgs10", response_model=ApiResponse)
async def trigger_update_dgs10(background_tasks: BackgroundTasks):
    """更新美债10年期利率"""
    filename = str(get_original_data_dir() / "dgs10_hist_df.csv")
    background_tasks.add_task(
        run_with_ws_notify,
        "美债10年期利率更新",
        update_dgs10,
        filename
    )
    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="美债10年期利率更新已启动",
        data=None
    )

@router.post("/update/cny", response_model=ApiResponse)
async def trigger_update_cny(background_tasks: BackgroundTasks):
    """更新美元兑人民币"""
    filename = str(get_original_data_dir() / "usdcny_df.csv")
    background_tasks.add_task(
        run_with_ws_notify,
        "美元兑人民币数据更新",
        update_usdcny,
        filename
    )
    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="美元兑人民币更新已启动",
        data=None
    )

@router.post("/update/brent", response_model=ApiResponse    )
async def trigger_update_brent(background_tasks: BackgroundTasks):
    """更新布伦特原油"""
    filename = str(get_original_data_dir() / "Brent_hist_df.csv")
    background_tasks.add_task(
        run_with_ws_notify,
        "布伦特原油数据更新",
        update_brent,
        filename
    )
    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="布伦特原油更新已启动",
        data=None
    )

@router.post("/update/spdr", response_model=ApiResponse)
async def trigger_update_spdr(background_tasks: BackgroundTasks):
    """更新 SPDR 黄金持仓"""
    filename = str(get_original_data_dir() / "SPDR_Gold_Holdings.csv")
    background_tasks.add_task(
        run_with_ws_notify,
        "SPDR黄金持仓数据更新",
        update_spdr_gold_holdings,
        filename
    )
    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="SPDR 持仓更新已启动",
        data=None
    )

@router.post("/update/kline", response_model=ApiResponse    )
async def trigger_update_kline(background_tasks: BackgroundTasks):
    """
    更新 Au99.99 分钟线（5分钟K线）
    华尔街见闻数据周末休市，但是实际上支付宝上等数据源周末该数据仍然在波动的
    """
    filename = str(get_original_data_dir() / "AU9999_SGE_10year_5min.csv")
    # checkpoint_dir 可以指定，这里直接使用 settings.DATA_DIR / "kline_checkpoint"
    background_tasks.add_task(
        run_with_ws_notify,
        "Au99.99 分钟线更新",
        update_kline_to_latest,
        "AU9999.SGE",
        filename,
        300
    )
    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="Au99.99 分钟线更新已启动",
        data=None
    )
