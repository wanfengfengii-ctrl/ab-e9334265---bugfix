import { groupKey } from "../lib/geometry";

/** 对位组明细表：与环形图联动高亮 */
export default function GroupTable({
  witness,
  diffKeys,
  activeGroup,
  pinnedGroup,
  onHoverGroup,
  onPinGroup,
}) {
  const effective = activeGroup ?? pinnedGroup;
  return (
    <div className="table-wrap result-table">
      <table className="group-table" data-testid="group-table">
        <thead>
          <tr>
            <th>组</th>
            <th>叶片</th>
            <th>参考和</th>
            <th>脉冲序号</th>
            <th>实测和</th>
            <th>绝对误差</th>
            <th>改动</th>
          </tr>
        </thead>
        <tbody>
          {witness.groups.map((g) => {
            const isDiff = diffKeys ? diffKeys.has(groupKey(g)) : false;
            const cls = [
              effective === g.index ? "active" : "",
              isDiff ? "is-diff" : "",
              g.modifications > 0 ? "has-mods" : "",
            ]
              .filter(Boolean)
              .join(" ");
            return (
              <tr
                key={g.index}
                data-testid={`group-row-${g.index}`}
                className={cls}
                onMouseEnter={() => onHoverGroup(g.index)}
                onMouseLeave={() => onHoverGroup(null)}
                onClick={() => onPinGroup(pinnedGroup === g.index ? null : g.index)}
              >
                <td>{g.index + 1}</td>
                <td>{g.refBlades.join(", ")}</td>
                <td>{g.refSum}</td>
                <td>{g.measIndices.map((t) => `#${t}`).join(", ")}</td>
                <td>{g.measSum}</td>
                <td>{g.absError}</td>
                <td>{g.modifications}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
