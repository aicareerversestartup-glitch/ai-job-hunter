import { useEffect, useState } from "react";
import { get } from "../api/client";
import { openExternal } from "../api/platform";
import type { Partner } from "../api/types";
import Icon from "../components/Icon";
import { useToast } from "../components/ui";

export default function Resources() {
  const toast = useToast();
  const [items, setItems] = useState<Partner[] | null>(null);
  useEffect(() => { get<Partner[]>("/api/partners").then(setItems).catch(() => setItems([])); }, []);
  const groups = (items ?? []).reduce<Record<string, Partner[]>>((acc, p) => {
    (acc[p.category] ??= []).push(p);
    return acc;
  }, {});

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Resources for your move</h1>
          <p>Services people often need when moving abroad for work. Some are partner links: we may earn a commission, at no extra cost to you. We never share your CV or details with them.</p>
        </div>
      </div>
      {items && items.length === 0 && <div className="empty"><p className="muted">No resources yet.</p></div>}
      {Object.entries(groups).map(([category, list]) => (
        <section className="panel" key={category}>
          <h2>{category}</h2>
          {list.map((p) => (
            <div className="entry spread" key={p.id}>
              <div style={{ flex: 1, minWidth: 220 }}>
                <strong>{p.name}</strong>
                <p className="muted" style={{ margin: "4px 0" }}>{p.description}</p>
                {p.countries.length > 0 && <div className="faint">Useful for: {p.countries.join(", ")}</div>}
                <div className="faint">{p.disclosure}</div>
              </div>
              <button className="btn" onClick={async () => {
                try { const r = await get<{ url: string }>(`/api/partners/${p.id}/go`); await openExternal(r.url); }
                catch (e) { toast((e as Error).message, "error"); }
              }}>Visit <Icon name="external" size={16} /></button>
            </div>
          ))}
        </section>
      ))}
    </>
  );
}
