# SHP 导入语义

一个上传请求可包含一个或多个数据集包。GeoJSON/GeoTIFF 每个文件自身构成一个包；Shapefile 包以不区分大小写的文件主名分组。

SHP 包的必需成员为 `.shp`、`.shx`、`.dbf`，可选成员为 `.prj`、`.cpg`。出现孤立成员、重复扩展名、主名不一致或缺失必需成员时，检查阶段失败且不得发布资产。

检查器在 Angelus 管理的上传目录中使用 GDAL/OGR 读取包；若依赖不可用，能力端点明确报告禁用原因。成功检查后，转换器把该包转换成 Angelus 管理的 GeoJSON 显示副本，保留字段、几何、CRS 和 `original_format=Shapefile` 来源信息。原始包仅留在导入私有存储，不给地图/API/Agent 返回路径。
