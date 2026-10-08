export default function BlurText({ text, className = "" }: { text: string; className?: string }) {
  const words = text.split(" ");
  return (
    <h1 className={className}>
      {words.map((word, index) => (
        <span
          key={`${word}-${index}`}
          className="blur-word"
          style={{ animationDelay: `${index * 90}ms` }}
        >
          {word}
          {index < words.length - 1 ? "\u00a0" : ""}
        </span>
      ))}
    </h1>
  );
}
