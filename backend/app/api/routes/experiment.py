from fastapi import APIRouter
from app.database.experiment_repo import experiment_repo
from app.schemas.common import ApiResponse, BusinessCode
from app.services.experiment_service import delete_experiment_by_id

router = APIRouter(prefix="/experiment", tags=["实验管理"])

@router.get("/list", response_model=ApiResponse)
async def list_experiments(limit: int = 1000):
    """获取最近实验列表"""
    exps = experiment_repo.list(limit=limit)
    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="成功",                        
        data={"experiments": exps}
    )

@router.get("/{exp_id}", response_model=ApiResponse)
async def get_experiment(exp_id: int):
    """获取单个实验详情"""
    exp = experiment_repo.get(exp_id)
    if exp is None:
        return ApiResponse(
            code=BusinessCode.NOT_FOUND,
            message="实验不存在",
            data=None
        )
    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message="成功",                       
        data=exp
    )

@router.delete("/{exp_id}")
async def api_delete_experiment(exp_id: int):
    """删除指定实验及其所有数据"""
    result = delete_experiment_by_id(exp_id)
    return ApiResponse(
        code=BusinessCode.SUCCESS,
        message=f"实验 #{exp_id} 已删除",                       
        data=None
    )
