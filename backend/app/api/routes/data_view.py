import os, glob
import pandas as pd
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from app.core.config import settings
from app.utils import get_original_data_dir, find_date_column, get_process_data_dir, get_experiment_root_dir
from app.schemas.common import ApiResponse, BusinessCode
from app.schemas.enums import DataDirType, SortOrder
from app.services.gold_data_service import get_gold_price_timeseries
from app.services.backtest_data_service import get_backtest_equity_curve
from app.services.realtime_data_service import get_realtime_equity_curve


router = APIRouter(prefix="/data-view", tags=["原始数据展示"])

@router.get("/status", response_model=ApiResponse)
async def original_data_status(dir_type: DataDirType = DataDirType.original):
    """返回所有原始数据文件的状态（递归扫描 1.OriginalData等数据目录）"""
    if dir_type == DataDirType.original:
        base_dir = get_original_data_dir()
    elif dir_type == DataDirType.processed:
        base_dir = get_process_data_dir()
    elif dir_type == DataDirType.experiment:
        base_dir = get_experiment_root_dir()
    else:
        return ApiResponse(code=BusinessCode.PARAM_ERROR, message="无效的目录类型")
    
    # 递归查找所有 CSV 文件
    csv_files = glob.glob(os.path.join(base_dir, "**", "*.csv"), recursive=True)
    files_info = []

    for fpath in csv_files:
        rel_path = os.path.relpath(fpath, base_dir).replace("\\", "/")
        try:
            df = pd.read_csv(fpath)
            if df.empty:
                files_info.append({
                    "file": rel_path,
                    "start_date" : "无数据",
                    "latest_date": "无数据",
                    "records": 0
                })
                continue

            date_col = find_date_column(df)
            if date_col:
                dates = pd.to_datetime(df[date_col], errors='coerce').dropna()
                first = dates.min().strftime('%Y-%m-%d') if len(dates) > 0 else "无日期"
                latest = dates.max().strftime('%Y-%m-%d') if len(dates) > 0 else "无日期"
            else:
                first = "无日期列"
                latest = "无日期列"

            files_info.append({
                "file": rel_path,
                "start_date" : first,
                "latest_date": latest,
                "records": len(df)
            })
        except Exception:
            files_info.append({
                "file": rel_path,
                "start_date" : "解析失败",
                "latest_date": "解析失败",
                "records": 0
            })

    # 将数据按照file字段升序排序
    files_info.sort(key=lambda x: x["file"])
    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="成功",
        data={"files": files_info}
    )
# {filename:path} 是 FastAPI 路径参数的一种特殊语法，
# 它告诉 FastAPI：filename 这个参数应该匹配 URL 中剩余的全部路径，包括斜杠 /。
@router.get("/data/{filename:path}", response_model=ApiResponse)
async def get_file_data(
    filename: str,
    dir_type: DataDirType = DataDirType.original,
    sort_date: SortOrder = SortOrder.off,
    page: int = Query(1, ge=1, description="页码"), # ge=1表示页码必须大于等于1
    page_size: int = Query(50, ge=1, le=500, description="每页条数")
):
    """
    返回指定 CSV 文件的数据
    - dir_type: 文件类型，用于确认获取文件的目录
    - filename: 文件名（相对于 dir_type 目录的路径，支持子目录，例如 data/subdir/file.csv）
    - sort_date: 是否按日期排序，默认值为 "off"，可选值为 "desc"（逆序）和 "asc"（正序）。如果用户请求排序但无法识别日期列，则会忽略排序请求并返回原始顺序的数据。  
    - page: 页码，默认值为 1
    - page_size: 每页条数，默认值为 50，最大值为 500
    """
    if dir_type == DataDirType.original:
        base_dir = get_original_data_dir()
    elif dir_type == DataDirType.processed:
        base_dir = get_process_data_dir()
    elif dir_type == DataDirType.experiment:
        base_dir = get_experiment_root_dir()
    else:
        return ApiResponse(code=BusinessCode.PARAM_ERROR, message="无效的目录类型")

    # 规范化路径并防止目录穿越
    # normpath会将路径中的..等特殊符号解析掉，join会将base_dir和filename拼接成一个完整路径
    # 该写法是为了防止传入filename = "../../../etc/passwd"类似的恶意路径
    filepath = os.path.normpath(os.path.join(base_dir, filename)) 
    if not filepath.startswith(os.path.normpath(base_dir)):
        raise HTTPException(status_code=403, detail="禁止访问")
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="文件不存在")
    if not filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="仅支持 CSV 文件")

    try:
        df = pd.read_csv(filepath)
        total = len(df)

        # 如果要求排序，则尝试识别日期列
        date_col = None
        if sort_date != "off":
            date_col = find_date_column(df)
            if date_col is not None:
                try:
                    # 排序前先判断原始数据是否包含非零的时间部分
                    # 取第一个有效值来检查
                     # 判断原始数据是否包含时间部分（通过查找冒号）
                    if not df[date_col].dropna().empty:
                        sample_str = str(df[date_col].dropna().iloc[0])
                        has_time = ':' in sample_str # 如果日期字符串中包含冒号，通常表示包含时间部分
                    else:
                        has_time = False

                    # 转换日期列（失败则保持原顺序）
                    df[date_col] = pd.to_datetime(df[date_col], errors='coerce') # coerce表示在转换失败时使用 NaT 替代
                    ascending = (sort_date == "asc")
                    df = df.sort_values(by=date_col, ascending=ascending, na_position='last') # na_position='last'表示将无法解析的日期（NaT）放在最后
                    
                    # 根据原始数据选择格式
                    date_fmt = '%Y-%m-%d %H:%M:%S' if has_time else '%Y-%m-%d'
                    df[date_col] = df[date_col].dt.strftime(date_fmt)
                except Exception:
                    # 排序失败，忽略，保持原始顺序
                    date_col = None

        # 分页
        start = (page - 1) * page_size
        end = start + page_size
        df_page = df.iloc[start:end]

        # 将 NaN 替换为 None，使其在 JSON 中显示为 null
        data = df_page.where(pd.notnull(df_page), None).to_dict(orient="records")
        result_data = {
            "filename": filename,
            "columns": df.columns.tolist(),
            "total": total,
            "page": page,
            "page_size": page_size,
            "data": data
        }
        if date_col:
            result_data["sort_applied"] = {
                "column": date_col,
                "order": sort_date
            }
        return ApiResponse(
            code=BusinessCode.SUCCESS,
            message="成功",
            data=result_data
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取文件失败: {str(e)}")

@router.get("/gold-prices", response_model=ApiResponse)
async def api_get_gold_prices(freq: str = "D"):
    """获取黄金价格时间序列（可用于图表）"""
    data = get_gold_price_timeseries(freq=freq)
    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="成功",
        data=data
    )


@router.get("/{exp_id}/backtest-data", response_model=ApiResponse)
async def api_get_backtest_data(exp_id: int):
    """获取实验的回测净值曲线及绩效摘要"""
    data = get_backtest_equity_curve(exp_id)
    return ApiResponse(code=BusinessCode.SUCCESS, message="成功", data=data)


@router.get("/{exp_id}/realtime-data", response_model=ApiResponse)
async def api_get_realtime_data(exp_id: int):
    """获取实验的实盘模拟数据"""
    data = get_realtime_equity_curve(exp_id)
    return ApiResponse(code=BusinessCode.SUCCESS, message="成功", data=data)