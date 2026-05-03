"use client";

import { CheckSquare, Square, ClipboardList } from "lucide-react";

interface TodoItem {
  done: boolean;
  text: string;
}

function parseTodos(md: string): TodoItem[] {
  const lines = md.split("\n");
  const items: TodoItem[] = [];
  for (const line of lines) {
    const m = line.match(/^[-*]\s+\[([ xX])\]\s+(.+)/);
    if (m) {
      items.push({ done: m[1].toLowerCase() === "x", text: m[2].trim() });
    }
  }
  return items;
}

interface Props {
  agentsMd: string;
}

export function AgentPlan({ agentsMd }: Props) {
  if (!agentsMd) return null;

  const todos = parseTodos(agentsMd);
  if (todos.length === 0) return null;

  const doneCount = todos.filter((t) => t.done).length;
  const pct = Math.round((doneCount / todos.length) * 100);

  return (
    <div className="border-b border-[var(--border)] px-4 py-3 bg-[var(--surface)]/60 flex-shrink-0">
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <ClipboardList size={13} className="text-blue-400 flex-shrink-0" />
        <span className="text-xs font-semibold text-gray-300">Kế hoạch Agent</span>
        <span className="ml-auto text-[10px] text-gray-600">{doneCount}/{todos.length}</span>

        {/* Progress bar */}
        <div className="w-16 h-1.5 bg-gray-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-blue-500 rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Todo list */}
      <div className="space-y-1 max-h-36 overflow-y-auto">
        {todos.map((item, i) => (
          <div key={i} className={`flex items-start gap-1.5 text-xs ${item.done ? "text-gray-600" : "text-gray-300"}`}>
            {item.done
              ? <CheckSquare size={12} className="text-green-500 flex-shrink-0 mt-0.5" />
              : <Square size={12} className="text-gray-600 flex-shrink-0 mt-0.5" />
            }
            <span className={item.done ? "line-through" : ""}>{item.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
