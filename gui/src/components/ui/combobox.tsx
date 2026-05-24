/**
 * Searchable combobox – a text input with a filtered dropdown list.
 *
 * Supports keyboard navigation (ArrowUp / ArrowDown / Enter / Escape),
 * click-to-select, and free-text entry when no option matches.
 */

import {
  useState,
  useRef,
  useEffect,
  useCallback,
  type KeyboardEvent,
} from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ComboboxOption {
  value: string;
  label: string;
}

export interface ComboboxProps {
  options: ComboboxOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  loading?: boolean;
  loadingText?: string;
  errorText?: string;
}

export function Combobox({
  options,
  value,
  onChange,
  placeholder,
  disabled,
  className,
  loading,
  loadingText = "Loading…",
  errorText,
}: ComboboxProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlightIdx, setHighlightIdx] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const displayValue = value || "";

  const filtered = query
    ? options.filter((o) => {
        const q = query.toLowerCase();
        return (
          o.value.toLowerCase().includes(q) ||
          o.label.toLowerCase().includes(q)
        );
      })
    : options;

  useEffect(() => {
    setHighlightIdx(-1);
  }, [query]);

  useEffect(() => {
    if (highlightIdx >= 0 && listRef.current) {
      const item = listRef.current.children[highlightIdx] as
        | HTMLElement
        | undefined;
      item?.scrollIntoView({ block: "nearest" });
    }
  }, [highlightIdx]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const select = useCallback(
    (val: string) => {
      onChange(val);
      setOpen(false);
      setQuery("");
      inputRef.current?.blur();
    },
    [onChange],
  );

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        setOpen(true);
        e.preventDefault();
      }
      return;
    }

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setHighlightIdx((prev) =>
          prev < filtered.length - 1 ? prev + 1 : 0,
        );
        break;
      case "ArrowUp":
        e.preventDefault();
        setHighlightIdx((prev) =>
          prev > 0 ? prev - 1 : filtered.length - 1,
        );
        break;
      case "Enter":
        e.preventDefault();
        if (highlightIdx >= 0 && highlightIdx < filtered.length) {
          select(filtered[highlightIdx].value);
        } else if (query.length > 0) {
          select(query);
        }
        break;
      case "Escape":
        e.preventDefault();
        setOpen(false);
        setQuery("");
        break;
    }
  }

  return (
    <div ref={containerRef} className={cn("relative", className)}>
      <input
        ref={inputRef}
        type="text"
        autoComplete="off"
        className="w-full rounded-md border bg-background py-1 pl-2 pr-7 text-sm"
        placeholder={placeholder}
        disabled={disabled}
        value={open ? query : displayValue}
        onFocus={() => {
          setOpen(true);
          setQuery("");
        }}
        onChange={(e) => {
          setQuery(e.target.value);
          if (!open) setOpen(true);
        }}
        onKeyDown={handleKeyDown}
      />
      <ChevronDown
        className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground"
        size={14}
      />

      {open && (
        <ul
          ref={listRef}
          className="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-md border bg-popover text-sm shadow-md"
        >
          {loading ? (
            <li className="px-2 py-1.5 text-muted-foreground">
              {loadingText}
            </li>
          ) : errorText ? (
            <li className="px-2 py-1.5 text-destructive">{errorText}</li>
          ) : filtered.length === 0 ? (
            <li className="px-2 py-1.5 text-muted-foreground">
              {query
                ? "No matches — press Enter to use custom value"
                : "No models available"}
            </li>
          ) : (
            filtered.map((opt, idx) => (
              <li
                key={opt.value}
                className={cn(
                  "cursor-pointer px-2 py-1.5 hover:bg-accent",
                  idx === highlightIdx && "bg-accent",
                  opt.value === value && "font-medium",
                )}
                onMouseDown={(e) => {
                  e.preventDefault();
                  select(opt.value);
                }}
                onMouseEnter={() => setHighlightIdx(idx)}
              >
                <span className="block truncate">{opt.value}</span>
                {opt.label !== opt.value && (
                  <span className="block truncate text-xs text-muted-foreground">
                    {opt.label}
                  </span>
                )}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
