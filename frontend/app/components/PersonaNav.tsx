import Link from "next/link";

const SECTIONS = [
  { href: "/researcher", label: "研究员门户", prefix: "R-", fallback: "R-101" },
  { href: "/admin", label: "数据管理员", prefix: "A-", fallback: "A-001" },
  { href: "/participant", label: "参与者门户", prefix: "P-", fallback: "P-001" },
];

export default function PersonaNav({ as }: { as: string }) {
  return (
    <nav className="topnav">
      <Link href={`/?as=${as}`} className="brand">
        研究数据平台
      </Link>
      <div className="navlinks">
        {SECTIONS.map((s) => (
          <Link
            key={s.href}
            href={`${s.href}?as=${as.startsWith(s.prefix) ? as : s.fallback}`}
          >
            {s.label}
          </Link>
        ))}
      </div>
      <span className="who">
        当前身份：<span className="mono">{as}</span>
      </span>
    </nav>
  );
}
