# 历史端点线索

源 korea-official-source-research，2026-11-16静态审查；本轮未重跑这些站的当前端点，不保留旧可达性矩阵和固定班次/价格。

- Jeju BIS：旧 `/publicTrafficInformation/getBusRouteNum`、`/schedule/viewNew/<线路>`、`/data/schedule/getScheduleTableInfo?scheduleId=...`，以及searchStationByKeyword/getNewStationInfoByStationId/getLineInfoByLineId。先从当前页面实际链接与请求确认，scheduleId、站ID、方向不要混用。参数用韩文时明确UTF-8。
- VisitJeju详情曾用 `/kr/detail/view?contentsid=...`。SSR/Nuxt可能嵌多层JSON，优先结构化解析并锚定对象；避免在整页跑高回溯正则，不能因搜不到ID就判整站JS空壳。
- 열린관광旧入口 `access.visitkorea.or.kr/ms/detail.do?cotId=...`；免税店协会旧 `/ko/member/dfs_list.php` 与dfs_view.php。列表先取真实ID，不写死编号含义。
- 门票附件先从当前公告链接定位，按xlsx关系与单元格类型读取；sharedStrings索引不是票价。可用当前spreadsheets能力处理。
- e-AC旧详情 `/portal/board/viewBoardDetail.do` 中bbsId曾为文章ID、flId为附件ID，需从本版列表链接确认。使领馆域名/语言路径以官网实际链接为准，不猜slug。

现行政策需要正文与修订链。镜像缺价格不证明官方无价格；域名历史归属不能替代当前官方关联验证。潮汐数据的station/日期/时区和来源版本必须一起记录。
