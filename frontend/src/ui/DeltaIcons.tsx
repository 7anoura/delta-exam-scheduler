/* DELTA_UI_PHASE18_3_ICONOIR — real Iconoir icons; no custom-drawn SVG paths. */
import * as Iconoir from 'iconoir-react'
import type { ComponentType, SVGProps } from 'react'

export type DeltaIconProps = SVGProps<SVGSVGElement> & {
  size?: number | string
  absoluteStrokeWidth?: boolean
}

const iconBank = Iconoir as unknown as Record<string, ComponentType<any>>

function fromIconoir(exportName: string): ComponentType<DeltaIconProps> {
  const Artwork = iconBank[exportName]
  function DeltaIcon({ size = 20, strokeWidth = 1.7, absoluteStrokeWidth: _unused, ...rest }: DeltaIconProps) {
    void _unused
    return <Artwork {...rest} width={size} height={size} strokeWidth={strokeWidth} aria-hidden={rest["aria-label"] ? undefined : true} />
  }
  DeltaIcon.displayName = `DeltaIcon(${exportName})`
  return DeltaIcon
}

export const Activity = fromIconoir('Activity')
export const AlertCircle = fromIconoir('WarningCircle')
export const ArrowDownToLine = fromIconoir('Download')
export const ArrowRight = fromIconoir('ArrowRight')
export const BarChart3 = fromIconoir('StatsReport')
export const BookOpen = fromIconoir('Book')
export const CalendarDays = fromIconoir('Calendar')
export const Check = fromIconoir('Check')
export const CheckCircle2 = fromIconoir('CheckCircle')
export const ChevronDown = fromIconoir('NavArrowDown')
export const CircleAlert = fromIconoir('WarningCircle')
export const CircleHelp = fromIconoir('HelpCircle')
export const ClipboardCheck = fromIconoir('TaskList')
export const Copy = fromIconoir('Copy')
export const ExternalLink = fromIconoir('OpenInWindow')
export const FileSpreadsheet = fromIconoir('Page')
export const FlaskConical = fromIconoir('Flask')
export const GraduationCap = fromIconoir('GraduationCap')
export const Layers3 = fromIconoir('ViewGrid')
export const LayoutDashboard = fromIconoir('Dashboard')
export const LockKeyhole = fromIconoir('Lock')
export const LogOut = fromIconoir('LogOut')
export const Menu = fromIconoir('Menu')
export const Printer = fromIconoir('Printer')
export const RefreshCw = fromIconoir('Refresh')
export const Save = fromIconoir('FloppyDisk')
export const Search = fromIconoir('Search')
export const ShieldAlert = fromIconoir('Shield')
export const ShieldCheck = fromIconoir('ShieldCheck')
export const Sparkles = fromIconoir('Network')
export const UserRoundCheck = fromIconoir('UserBadgeCheck')
export const Users2 = fromIconoir('Group')
export const X = fromIconoir('Xmark')

/* Mapping is generated from verified iconoir-react exports at install time. */
