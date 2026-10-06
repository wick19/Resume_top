export default function GradientText({
  children,
  tone = "ink",
}: {
  children: string;
  tone?: "ink" | "light";
}) {
  const gradient =
    tone === "light"
      ? "bg-gradient-to-r from-[#eef3fb] to-[#9ad7ff]"
      : "bg-gradient-to-r from-primary to-accent";
  return <span className={`${gradient} bg-clip-text text-transparent`}>{children}</span>;
}
