import {
  Activity, AlertTriangle, BarChart3, Bot, BookOpen, Boxes, Brain, Briefcase, CheckCircle2, ChevronDown, ChevronRight,
  CircleDot, ClipboardList, Compass, Cpu, Database, Download, Factory, FileText, FlaskConical, Folder, FolderKanban,
  Gauge, GitBranch, Headset, Home, Info, Landmark, Layers, Lightbulb, LineChart, ListChecks, Loader2, Lock, Map,
  Megaphone, MessageCircle, Moon, Play, Plus, Radar, RefreshCw, Rocket, Ruler, Scale, ScatterChart, Search, Send,
  Settings, ShieldAlert, ShieldCheck, ShoppingBasket, Sigma, Sliders, Sparkles, Sun, Table2, Tag, Target, Trash2,
  TrendingUp, Truck, Unlock, Upload, Users, Wand2, Wrench, X, XCircle, type LucideIcon,
} from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  activity: Activity, alert: AlertTriangle, "bar-chart": BarChart3, bot: Bot, "book-open": BookOpen, book: BookOpen,
  boxes: Boxes, brain: Brain, briefcase: Briefcase, check: CheckCircle2, "chevron-down": ChevronDown,
  "chevron-right": ChevronRight, dot: CircleDot, clipboard: ClipboardList, compass: Compass, cpu: Cpu, database: Database,
  download: Download, factory: Factory, "file-text": FileText, flask: FlaskConical, folder: Folder, projects: FolderKanban,
  gauge: Gauge, branch: GitBranch, headset: Headset, home: Home, info: Info, landmark: Landmark, layers: Layers,
  lightbulb: Lightbulb, "line-chart": LineChart, "list-checks": ListChecks, loader: Loader2, lock: Lock, unlock: Unlock,
  map: Map, megaphone: Megaphone, "message-circle": MessageCircle, moon: Moon, play: Play, plus: Plus, radar: Radar,
  refresh: RefreshCw, rocket: Rocket, ruler: Ruler, scale: Scale, scatter: ScatterChart, search: Search, send: Send,
  settings: Settings, "shield-alert": ShieldAlert, "shield-check": ShieldCheck, "shopping-basket": ShoppingBasket,
  sigma: Sigma, sliders: Sliders, sparkles: Sparkles, sun: Sun, table: Table2, tag: Tag, target: Target, trash: Trash2,
  "trending-up": TrendingUp, truck: Truck, upload: Upload, users: Users, wand: Wand2, wrench: Wrench, x: X,
  "x-circle": XCircle,
};

export function Icon({ name, size = 16, className, style }: { name: string; size?: number; className?: string; style?: React.CSSProperties }) {
  const C = ICONS[name] ?? CircleDot;
  return <C size={size} className={className} style={style} aria-hidden />;
}
