export default function Badge({
  label,
  cls,
}: {
  label: string;
  cls: string;
}) {
  return <span className={`badge ${cls}`}>{label}</span>;
}
