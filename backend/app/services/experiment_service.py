# app/services/experiment_service.py
import shutil
import logging
from pathlib import Path
from app.database.experiment_repo import experiment_repo
from app.utils.data_utils import get_experiment_dir, get_root_data_dir
from app.schemas.enums import DataPathType
from app.utils.exceptions import BusinessError

logger = logging.getLogger(__name__)

def delete_experiment_by_id(exp_id: int):
    """
    删除实验：先删除数据目录，再删除数据库记录。
    """
    # 1. 获取实验信息（用于构建目录）
    exp = experiment_repo.get(exp_id)
    if not exp:
        raise BusinessError(f"实验 #{exp_id} 不存在")

    # 2. 删除实验文件夹（整个 {id}_{name} 目录）
    # 注意：get_experiment_dir 需要 experiment_name，并传入 DataPathType.base 获取实验根目录
    exp_name = exp.get('experiment_name', 'unknown')
    exp_root_dir = get_experiment_dir(exp_id, exp_name, DataPathType.base)
    if exp_root_dir.exists():
        shutil.rmtree(exp_root_dir)
        logger.info("已删除实验目录: %s", exp_root_dir)
    else:
        logger.warning("实验目录不存在，跳过删除: %s", exp_root_dir)

    # 3. 删除数据库记录
    success = experiment_repo.delete(exp_id)
    if not success:
        # 理论上不会发生，因为前面已经查到记录
        raise BusinessError(f"删除数据库记录失败")

    return {"id": exp_id, "deleted": True}