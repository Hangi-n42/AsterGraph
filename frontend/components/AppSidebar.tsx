"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type ActiveMenu = "knowledge";

interface AppSidebarProps {
  activeMenu: ActiveMenu;
}

export default function AppSidebar({ activeMenu }: AppSidebarProps) {
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);

  const handle = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (collapsed) handle.current?.focus(); }, [collapsed]);

  function menuClass(menu: ActiveMenu) {
    const isActive = activeMenu === menu;
    return isActive
      ? "w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 text-left font-semibold text-slate-900 shadow-sm"
      : "w-full rounded-md px-3 py-2.5 text-left font-semibold text-slate-700 hover:bg-slate-200";
  }

  const navigationItems: Array<{ key: ActiveMenu; label: string; path: string; className?: string }> = [
    { key: "knowledge", label: "회사 지식 자료", path: "/knowledge" },
  ];

  return (
    <div className={`relative flex-shrink-0 transition-all duration-200 ${collapsed ? "w-0" : "w-52"}`}>
      {/* Sidebar panel - absolute so main can expand when collapsed */}
      <aside inert={collapsed}
        className={`absolute left-0 top-0 h-full border-r border-slate-300 bg-[#d9dee7] flex flex-col transform transition-transform duration-200 ${
          collapsed ? "-translate-x-full" : "translate-x-0 w-52"
        }`}
      >
        <div className="flex items-center justify-between border-b border-slate-300 px-4 py-4 text-xl font-black tracking-tight text-slate-900">
          <span>AsterGraph</span>
          <button
            type="button"
            aria-label={collapsed ? "열기" : "접기"}
            onClick={() => setCollapsed((s) => !s)}
            className="text-sm p-1 rounded hover:bg-slate-200"
          >
            {collapsed ? "▶" : "◀"}
          </button>
        </div>

        <div className="flex-1 px-2 py-6 text-sm">
          {navigationItems.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => router.push(item.path)}
              className={`${item.className || ""} ${menuClass(item.key)}`.trim()}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="border-t border-slate-300 px-3 py-4 text-[10px] text-slate-500">© AsterGraph System</div>
      </aside>

      {/* Small visible handle when collapsed */}
      {collapsed && (
        <button
          type="button"
          aria-label="사이드바 열기"
          ref={handle}
          onClick={() => setCollapsed(false)}
          className="absolute left-0 top-6 -ml-3 z-40 flex h-8 w-6 items-center justify-center rounded-r-md bg-slate-900 text-white shadow"
        >
          <span className="text-sm">▶</span>
        </button>
      )}
    </div>
  );
}
