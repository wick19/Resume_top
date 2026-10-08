import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type ReactNode, type UIEvent } from "react";
import { motion, useInView, useReducedMotion } from "motion/react";

type AnimatedItemProps = {
  children: ReactNode;
  delay?: number;
  index: number;
  hold?: boolean;
  onMouseEnter?: () => void;
};

function AnimatedItem({ children, delay = 0, index, hold = false, onMouseEnter }: AnimatedItemProps) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { amount: 0.5, once: false });
  const reduce = useReducedMotion();
  const shown = reduce || hold || inView;

  return (
    <motion.div
      ref={ref}
      data-index={index}
      onMouseEnter={onMouseEnter}
      initial={reduce ? false : { scale: 0.7, opacity: 0 }}
      animate={shown ? { scale: 1, opacity: 1 } : { scale: 0.7, opacity: 0 }}
      transition={{ duration: 0.22, delay }}
      className="mb-3"
    >
      {children}
    </motion.div>
  );
}

type AnimatedListProps<T> = {
  items: T[];
  renderItem: (item: T, index: number, selected: boolean) => ReactNode;
  onItemSelect?: (item: T, index: number) => void;
  getKey?: (item: T, index: number) => string | number;
  holdIndex?: number;
  showGradients?: boolean;
  enableArrowNavigation?: boolean;
  className?: string;
  displayScrollbar?: boolean;
  initialSelectedIndex?: number;
};

export default function AnimatedList<T>({
  items,
  renderItem,
  onItemSelect,
  getKey,
  holdIndex = -1,
  showGradients = true,
  enableArrowNavigation = true,
  className = "",
  displayScrollbar = true,
  initialSelectedIndex = -1,
}: AnimatedListProps<T>) {
  const listRef = useRef<HTMLDivElement>(null);
  const [selectedIndex, setSelectedIndex] = useState(initialSelectedIndex);
  const [keyboardNav, setKeyboardNav] = useState(false);
  const [topGradientOpacity, setTopGradientOpacity] = useState(0);
  const [bottomGradientOpacity, setBottomGradientOpacity] = useState(0);

  const measure = useCallback((node: HTMLDivElement) => {
    const overflow = node.scrollHeight - node.clientHeight;
    setTopGradientOpacity(Math.min(node.scrollTop / 50, 1));
    const bottomDistance = node.scrollHeight - (node.scrollTop + node.clientHeight);
    setBottomGradientOpacity(overflow <= 1 ? 0 : Math.min(bottomDistance / 50, 1));
  }, []);

  useEffect(() => {
    const node = listRef.current;
    if (!node) return;
    measure(node);
    const observer = new ResizeObserver(() => measure(node));
    observer.observe(node);
    return () => observer.disconnect();
  }, [items.length, holdIndex, measure]);

  const handleScroll = (event: UIEvent<HTMLDivElement>) => {
    measure(event.currentTarget);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!enableArrowNavigation || !items.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setKeyboardNav(true);
      setSelectedIndex((prev) => Math.min(prev + 1, items.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setKeyboardNav(true);
      setSelectedIndex((prev) => Math.max(prev - 1, 0));
    } else if (event.key === "Enter" && event.target === listRef.current && selectedIndex >= 0 && selectedIndex < items.length) {
      event.preventDefault();
      onItemSelect?.(items[selectedIndex], selectedIndex);
    }
  };

  useEffect(() => {
    if (!keyboardNav || selectedIndex < 0 || !listRef.current) return;
    const container = listRef.current;
    const selectedItem = container.querySelector(`[data-index="${selectedIndex}"]`) as HTMLElement | null;
    if (selectedItem) {
      const extraMargin = 50;
      const containerScrollTop = container.scrollTop;
      const containerHeight = container.clientHeight;
      const itemTop = selectedItem.offsetTop;
      const itemBottom = itemTop + selectedItem.offsetHeight;
      if (itemTop < containerScrollTop + extraMargin) {
        container.scrollTo({ top: itemTop - extraMargin, behavior: "smooth" });
      } else if (itemBottom > containerScrollTop + containerHeight - extraMargin) {
        container.scrollTo({ top: itemBottom - containerHeight + extraMargin, behavior: "smooth" });
      }
      selectedItem.querySelector<HTMLElement>("button")?.focus();
    }
    setKeyboardNav(false);
  }, [selectedIndex, keyboardNav]);

  return (
    <div className={`lib-animated relative w-full ${className}`}>
      <div
        ref={listRef}
        className={`lib-animated-scroll max-h-[32rem] overflow-y-auto p-2 ${displayScrollbar ? "" : "lib-animated-hide-bar"}`}
        onScroll={handleScroll}
        onKeyDown={onKeyDown}
        tabIndex={0}
        role="list"
        aria-label="Tailored resumes"
      >
        {items.map((item, index) => (
          <AnimatedItem
            key={getKey ? getKey(item, index) : index}
            delay={index * 0.06}
            index={index}
            hold={index === holdIndex}
            onMouseEnter={() => setSelectedIndex(index)}
          >
            {renderItem(item, index, selectedIndex === index)}
          </AnimatedItem>
        ))}
      </div>
      {showGradients && (
        <>
          <div className="lib-animated-fade is-top" style={{ opacity: topGradientOpacity }} />
          <div className="lib-animated-fade is-bottom" style={{ opacity: bottomGradientOpacity }} />
        </>
      )}
    </div>
  );
}
