"use client";

import React from "react";
import { create } from "zustand";
import { useAPI } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Tooltip } from '@/components/ui/tooltip';

// ---------------- UI PRIMITIVES ----------------
const cx = (...c: (string | false | undefined)[]) => c.filter(Boolean).join(" ");
const Card = ({ children, className = "" }: React.PropsWithChildren<{ className?: string }>) => (
  <div className={cx("rounded-2xl bg-white shadow-sm ring-1 ring-gray-200/60", className)}>{children}</div>
);
const CardHeader = ({ children }: React.PropsWithChildren) => (
  <div className="p-5 border-b border-gray-100 rounded-t-2xl bg-gray-50/60">{children}</div>
);
const CardTitle = ({ children, className = "" }: React.PropsWithChildren<{ className?: string }>) => (
  <h3 className={cx("font-semibold text-lg", className)}>{children}</h3>
);
const CardContent = ({ children, className = "" }: React.PropsWithChildren<{ className?: string }>) => (
  <div className={cx("p-5", className)}>{children}</div>
);
const Button = ({ children, onClick, disabled, variant = "primary", className = "", full = false }: { children: React.ReactNode; onClick?: () => void; disabled?: boolean; variant?: "primary" | "secondary" | "ghost"; className?: string; full?: boolean; }) => (
  <button onClick={onClick} disabled={disabled} className={cx("rounded-xl px-5 py-3 font-medium transition", full && "w-full", variant === "primary" && "bg-blue-600 !text-white hover:bg-blue-700 disabled:opacity-50", variant === "secondary" && "bg-white text-gray-900 ring-1 ring-gray-300 hover:bg-gray-50", variant === "ghost" && "bg-transparent text-gray-700 hover:bg-gray-100", className)}>{children}</button>
);
const Textarea = (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea {...props} className={cx("w-full text-xl leading-7 p-6 rounded-2xl ring-1 ring-gray-300 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-600", props.className)} />
);
const Input = (props: React.InputHTMLAttributes<HTMLInputElement>) => (
  <input {...props} className={cx("w-full rounded-xl ring-1 ring-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-600", props.className)} />
);
const Chip = ({ active, children, onClick }: { active?: boolean; children: React.ReactNode; onClick?: () => void }) => (
  <button type="button" onClick={onClick} className={cx("px-3 py-2 rounded-full text-sm transition ring-1", active ? "bg-blue-600 !text-white ring-blue-600" : "bg-white text-gray-900 ring-gray-300 hover:bg-gray-50")}>{children}</button>
);

// ---------------- TYPES & CONSTANTS ----------------
const SCOPE_CHIPS = {
  Populations: ["Individuals", "Vulnerable groups", "Organizations"],
  Methods: ["Pilots", "RCTs", "Surveys"],
  Outcomes: ["Economic impacts", "Environmental impacts", "Social impacts"],
} as const;
const EXCLUDE_CHIPS = ["Industry", "Opinion pieces", "Modeling-only", "Non-English"] as const;
// Special regions and country list from v1 search form
const SPECIAL_REGIONS = [
  'All',
  'UK',
  'All but UK',
  'OECD members',
  'Non-OECD members',
  'G20',
  'G7',
  'North America',
  'South and Central America',
  'Europe',
  'Nordics',
  'APAC',
  'Africa',
];

const COUNTRY_LIST = [
  'USA', 'Spain', 'Japan', 'Canada', 'Germany', 'Sweden', 'Australia', 'France', 'Brazil', 'Netherlands', 'Italy', 'Portugal', 'Peru', 'Mexico', 'Turkey', 'Austria', 'Singapore', 'China', 'Switzerland', 'Belgium', 'Philippines', 'South Africa', 'Ireland', 'Denmark', 'Taiwan', 'Uruguay', 'Colombia', 'Romania', 'Finland', 'Thailand', 'Norway', 'Czech Republic', 'Chile', 'Indonesia', 'New Zealand', 'India', 'Argentina', 'Tanzania', 'Latvia', 'Slovakia', 'Lithuania', 'Slovenia', 'Bulgaria', 'Iceland', 'Greece', 'Paraguay', 'Hungary', 'Luxembourg', 'Estonia', 'Ukraine', 'Morocco', 'Serbia', 'Trinidad and Tobago', 'Cyprus', 'Ecuador', 'Georgia', 'Moldova', 'South Korea', 'Sri Lanka', 'Malaysia', 'Uganda', 'Kosovo', 'North Macedonia', 'Lebanon', 'El Salvador', 'Honduras', 'Belarus', 'Micronesia', 'Russia', 'Panama', 'Israel', 'Kenya', 'Maldives', 'Iran', 'Bosnia and Herzegovina', 'Afghanistan', 'Egypt', 'Croatia', 'Barbados', 'Bolivia', 'Tunisia', 'Vietnam', 'Costa Rica', 'Mauritius', 'Oman', 'Jamaica', 'Nigeria', 'Montenegro', 'Bahamas', 'Iraq', 'Cambodia', 'Bangladesh', 'Azerbaijan', 'Nepal', 'Ghana', 'Mongolia', 'Timor Leste', 'Bhutan', 'Cameroon', 'Brunei', 'Liberia', 'Saudi Arabia', 'Ethiopia', 'Pakistan', 'Papua New Guinea', 'Venezuela', 'Namibia', 'Albania', 'Guyana', 'Syria', 'Nicaragua', 'Kyrgyzstan', 'Malta', 'Haiti', 'Cape Verde', 'Samoa', 'Uzbekistan', 'Qatar', 'Myanmar', 'Benin', 'Mauritania', 'Mozambique', 'Algeria', 'Zambia', 'Solomon Islands', 'Kiribati', 'Kuwait', 'Armenia', 'Jordan', 'Burkina Faso', 'Andorra', 'Palau', 'Botswana', 'Mali', 'Bahrain', 'Rwanda', 'Senegal', 'Belize', 'United Arab Emirates', 'Fiji', 'Vanuatu', 'Libya', 'Suriname', 'Cuba', 'Laos', 'Togo', 'Tonga', 'Eswatini', 'Angola', 'Tajikistan', 'Ivory Coast', 'Guinea', 'Zimbabwe', 'Malawi', 'Marshall Islands', 'Burundi', 'Niger', 'Madagascar', 'Sudan', 'Somalia', 'Turkmenistan', 'Tuvalu', 'Seychelles', 'South Sudan', 'Sao Tome and Principe', 'Central African Republic', 'Sierra Leone', 'Yemen', 'Democratic Republic Of The Congo', 'San Marino', 'Chad', 'Palestine', 'Vatican City', 'Nauru', 'Kazakhstan', 'Equatorial Guinea', 'Lesotho', 'Monaco', 'North Korea', 'Saint Kitts and Nevis', 'Liechtenstein', 'Djibouti', 'Comoros', 'Gambia', 'Gabon', 'Eritrea', 'Guinea-Bissau'
];

// Quick access countries for chips
const COUNTRIES = [
  "UK", 
  "US", 
  "Canada", 
  "Australia",
  "OECD members", 
  "G20", 
  "G7",
  "Europe", 
  "North America", 
  "APAC"
];


type Step = "ASK" | "REFINE" | "APPROVE";
// Refine flow: 0 SubQs → 1 Sources → 2 Time → 3 Geography → 4 Focus → 5 Exclude
type RefineStep = 0 | 1 | 2 | 3 | 4 | 5;
type TimePreset = "LAST_YEAR" | "LAST_5_YEARS" | "SINCE_2000" | "ANY" | "CUSTOM";
type Access = { academic: boolean; policy: boolean };

type DirectCriteria = {
  sources: ("openalex" | "overton")[];
  access: Access;
  geography?: string[]; // multi-select
  timePreset?: TimePreset; timeFrom?: string; timeTo?: string;
  mode: "semantic" | "boolean";
  limit: number;
  relevanceFiltering: boolean;
  abstractsOnly: boolean;
  query: string;
};

type SoftCriteria = { include: string[]; exclude: string[]; };

type Brief = {
  researchQuestion: string;
  subQuestions: string[];
  direct: DirectCriteria;
  soft: SoftCriteria;
};

// ---------------- STATE ----------------
interface ChatState {
  step: Step;
  refineStep: RefineStep;
  researchQuestion: string;
  timePreset: TimePreset; customFrom?: string; customTo?: string;
  geography: string[];
  access: Access;
  scope: string[]; customFocus: string[];
  excludes: string[]; customExcludes: string[];
  subQuestions: string[];
  autoGeneratedSuggestions: string[];
  showPlan: boolean;
  editableQuery?: string;
  isGeneratingSubQuestions: boolean;
  maxResults: number;
  set: (p: Partial<ChatState>) => void;
  next: () => void; back: () => void;
  nextRefine: () => void; backRefine: () => void;
}

export const useChat = create<ChatState>((set, get) => ({
  step: "ASK",
  refineStep: 0,
  researchQuestion: "",
  timePreset: "LAST_5_YEARS",
  geography: [],
  access: { academic: true, policy: true },
  scope: [], customFocus: [],
  excludes: [], customExcludes: [],
  subQuestions: [],
  autoGeneratedSuggestions: [],
  showPlan: false,
  editableQuery: "",
  isGeneratingSubQuestions: false,
  maxResults: 30,
  set: (p) => set(p),
  next: () => {
    const s = get();
    let maxResults = s.maxResults;
    // Smart defaults heuristics
    if ((s.subQuestions?.length || 0) >= 2) maxResults = Math.max(maxResults, 50);
    if ((s.geography?.length || 0) >= 2) maxResults = Math.max(maxResults, 60);
    set({ step: s.step === "ASK" ? "REFINE" : "APPROVE", maxResults });
  },
  back: () => set({ step: get().step === "APPROVE" ? "REFINE" : "ASK" }),
  nextRefine: () => set({ refineStep: (Math.min(5, get().refineStep + 1)) as RefineStep }),
  backRefine: () => set({ refineStep: (Math.max(0, get().refineStep - 1)) as RefineStep }),
}));

// ---------------- PLAN BUILDER ----------------
function buildPlan(state: {
  researchQuestion: string;
  subQuestions: string[];
  timePreset: TimePreset; customFrom?: string; customTo?: string;
  geography: string[];
  access: Access;
  scope: string[]; customFocus: string[];
  excludes: string[]; customExcludes: string[];
  editableQuery?: string;
  maxResults: number;
}): Brief {
  const tokens: string[] = [];
  const rq = (state.researchQuestion || "").trim();
  if (rq) tokens.push(`(${rq})`);

  if (state.subQuestions?.length) {
    const subQ = state.subQuestions.map(q => q.trim()).filter(Boolean).map(q => `(${q})`).join(" OR ");
    if (subQ) tokens.push(`(${subQ})`);
  }

  // Geography OR-group (skip OECD token)
  const geos = (state.geography || []).filter(g => g && g !== "OECD");
  if (geos.length === 1) tokens.push(geos[0]);
  if (geos.length > 1) tokens.push(`(${geos.map(g=>`"${g}"`).join(" OR ")})`);

  // Focus chips → synonyms
  const scopeAll = [...new Set([...(state.scope||[]), ...(state.customFocus||[])])];
  if (scopeAll.includes("Individuals")) tokens.push("(individual* OR people OR person* OR citizen*)");
  if (scopeAll.includes("Vulnerable groups")) tokens.push("(vulnerable OR disadvantaged OR marginalized OR at-risk)");
  if (scopeAll.includes("Organizations")) tokens.push("(organization* OR organisation* OR firm* OR business* OR company OR companies OR institution*)");
  if (scopeAll.includes("Pilots")) tokens.push("(pilot OR trial OR demonstration OR test*)");
  if (scopeAll.includes("RCTs")) tokens.push("(randomized OR randomised OR RCT OR \"controlled trial\")");
  if (scopeAll.includes("Surveys")) tokens.push("(survey OR questionnaire OR poll OR interview*)");
  if (scopeAll.includes("Economic impacts")) tokens.push("(cost* OR economic OR financial OR budget OR spending OR revenue)");
  if (scopeAll.includes("Environmental impacts")) tokens.push("(environment* OR ecological OR sustainability OR emission* OR carbon OR climate)");
  if (scopeAll.includes("Social impacts")) tokens.push("(social OR equity OR fairness OR inequality OR distributional OR wellbeing OR \"well-being\")");

  // Custom focus terms become OR group
  const customFocus = (state.customFocus||[]).map(t=>t.trim()).filter(Boolean);
  if (customFocus.length) tokens.push(`(${customFocus.map(t=>`"${t}"`).join(" OR ")})`);

  // Exclusions
  const exTokens: string[] = [];
  const excludesAll = [...new Set([...(state.excludes||[]), ...(state.customExcludes||[])])];
  if (excludesAll.includes("Industry")) exTokens.push("NOT (industry OR commercial)");
  if (excludesAll.includes("Modeling-only")) exTokens.push("NOT (simulation AND NOT (trial OR experiment))");
  if (excludesAll.includes("Opinion pieces")) exTokens.push("NOT editorial NOT commentary");
  // Non-English → positive include
  if (excludesAll.includes("Non-English")) tokens.push("language:English");

  const autoQuery = [tokens.join(" AND "), exTokens.join(" AND ")].filter(Boolean).join(" AND ");
  const finalQuery = (state.editableQuery && state.editableQuery.trim()) || autoQuery;

  // Map time presets to actual dates
  let timeFrom: string | undefined;
  let timeTo: string | undefined;
  
  if (state.timePreset === "CUSTOM") {
    timeFrom = state.customFrom;
    timeTo = state.customTo;
  } else if (state.timePreset !== "ANY") {
    const now = new Date();
    timeTo = now.toISOString().split('T')[0]; // today
    
    switch (state.timePreset) {
      case "LAST_YEAR":
        timeFrom = new Date(now.getFullYear() - 1, now.getMonth(), now.getDate()).toISOString().split('T')[0];
        break;
      case "LAST_5_YEARS":
        timeFrom = new Date(now.getFullYear() - 5, now.getMonth(), now.getDate()).toISOString().split('T')[0];
        break;
      case "SINCE_2000":
        timeFrom = "2000-01-01";
        break;
    }
  }

  // Build sources array based on user selection
  const sources: ("openalex" | "overton")[] = [];
  if (state.access.academic) sources.push("openalex");
  if (state.access.policy) sources.push("overton");

  const direct: DirectCriteria = {
    sources,
    access: state.access,
    geography: state.geography,
    timePreset: state.timePreset,
    timeFrom,
    timeTo,
    mode: "semantic",
    limit: state.maxResults,
    relevanceFiltering: true,
    abstractsOnly: false,
    query: finalQuery,
  };

  const brief: Brief = {
    researchQuestion: rq,
    subQuestions: state.subQuestions || [],
    direct,
    soft: { include: scopeAll, exclude: excludesAll },
  };

  return brief;
}

// ---------------- HELPERS ----------------
function ProgressBar({ step, total }: { step: number; total: number }) {
  const pct = Math.round(((step + 1) / total) * 100);
  return (
    <div className="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
      <div className="h-full bg-blue-600" style={{ width: `${pct}%` }} />
    </div>
  );
}

// ---------------- PLAN DRAWER ----------------
function PlanDrawer() {
  const s = useChat();
  const brief = buildPlan({
    researchQuestion: s.researchQuestion,
    subQuestions: s.subQuestions,
    timePreset: s.timePreset,
    customFrom: s.customFrom,
    customTo: s.customTo,
    geography: s.geography,
    access: s.access,
    scope: s.scope,
    customFocus: s.customFocus,
    excludes: s.excludes,
    customExcludes: s.customExcludes,
    editableQuery: s.editableQuery,
    maxResults: s.maxResults,
  });
  const d = brief.direct;

  return (
    <div className="mt-4 rounded-2xl ring-1 ring-gray-200">
      <div className="p-4 bg-gray-50 rounded-t-2xl flex items-center justify-between">
        <div className="font-medium">Search plan</div>
      </div>
      <div className="p-4 space-y-3 text-sm">
        <div>
          <textarea
            value={(s.editableQuery && s.editableQuery.length) ? s.editableQuery : d.query}
            onChange={(e)=>s.set({ editableQuery: (e.target as HTMLTextAreaElement).value })}
            className="w-full rounded-xl ring-1 ring-gray-300 p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600"
            rows={4}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div><span className="font-medium">Time</span><br />{(d.timePreset||"ANY").replaceAll("_"," ")}</div>
          <div><span className="font-medium">Sources</span><br />{d.sources.join(", ")}</div>
          {d.geography?.length ? (<div><span className="font-medium">Geography</span><br />{d.geography.join(", ")}</div>) : null}
          <div><span className="font-medium">Access</span><br />{[d.access.academic && "academic", d.access.policy && "policy"].filter(Boolean).join(", ")}</div>
          <div>
            <span className="font-medium">Max results</span><br />
            <div className="mt-1 flex flex-wrap gap-2">
              {[5, 10, 20, 30, 50, 100].map(n => (
                <button
                  key={n}
                  onClick={() => s.set({ maxResults: n })}
                  className={`px-3 py-1.5 rounded-full text-sm ring-1 ${
                    s.maxResults === n
                      ? "bg-blue-600 !text-white ring-blue-600"
                      : "bg-white text-gray-900 ring-gray-300 hover:bg-gray-50"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------- SCREENS ----------------
function ScreenAsk() {
  const s = useChat();
  const { generateSubQuestions } = useAPI();

  const handleNext = async () => {
    const researchQuestion = s.researchQuestion.trim();
    if (!researchQuestion) return;

    // Auto-generate sub-question suggestions (replace manual ones)
    s.set({ isGeneratingSubQuestions: true });
    
    try {
      // Generate sub-questions
      const response = await generateSubQuestions(researchQuestion);
      const suggestions = response?.sub_questions || [];
      
      s.set({ 
        autoGeneratedSuggestions: suggestions,
        step: "REFINE"
      });
    } catch (error) {
      console.error('Failed to generate suggestions:', error);
      // Continue without auto-generated content if generation fails
      s.set({ 
        autoGeneratedSuggestions: [],
        step: "REFINE" 
      });
    } finally {
      s.set({ isGeneratingSubQuestions: false });
    }
  };

  const handleQuickSearch = () => {
    // Skip to approve step with current question only
    s.set({ step: "APPROVE" });
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8 pt-32">
      {/* Header */}
      <div className="text-center space-y-0">
        <div className="flex items-center justify-center gap-3">
          <h1 className="text-4xl font-bold tracking-tight">Find global policy evidence</h1>
          <Tooltip content={
            <p className="max-w-xs">
              Alpha means this is an early prototype with limited functionality. 
              Features may be incomplete, unstable, or subject to change. 
              We&apos;re actively developing and improving the tool.
            </p>
          }>
            <Badge variant="default" className="text-sm bg-blue-600 hover:bg-blue-700 text-white font-semibold px-3 py-1 -mt-2">ALPHA</Badge>
          </Tooltip>
        </div>
      </div>

      {/* Search Form */}
      <div className="space-y-6">
        <Textarea autoFocus placeholder="Example: Interventions to improve home learning environment for young children" value={s.researchQuestion} onChange={(e) => s.set({ researchQuestion: e.target.value })} />
        <div className="space-y-4 mt-12">
          <div className="flex gap-3">
            <Button 
              variant="secondary"
              full
              disabled={!s.researchQuestion.trim()}
              onClick={handleQuickSearch}
            >
              Quick search
            </Button>
            <Button 
              full 
              disabled={!s.researchQuestion.trim() || s.isGeneratingSubQuestions} 
              onClick={handleNext}
            >
              {s.isGeneratingSubQuestions ? 'Generating questions...' : 'Refine search'}
            </Button>
          </div>
          <div className="text-center pt-2">
            <button 
              className="text-sm text-gray-700 bg-gray-100 hover:bg-gray-200 px-4 py-2 rounded-lg transition-colors border-0" 
              onClick={() => s.set({ showPlan: !s.showPlan })}
            >
              {s.showPlan ? 'Hide search plan ▾' : 'Show search plan ▸'}
            </button>
          </div>
        </div>
      </div>
      {s.showPlan && <PlanDrawer />}
    </div>
  );
}

function StepSubQuestions() {
  const s = useChat();
  const [val, setVal] = React.useState("");

  return (
    <div className="space-y-6">
      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Would you like to add sub-questions?</h2>
        <p className="text-gray-600 text-lg">These are optional and will expand your search alongside your main question.</p>
      </div>
      
      <div className="flex flex-wrap gap-3 justify-center">
        {/* Show auto-generated suggestions */}
        {s.autoGeneratedSuggestions.map((q) => (
          <Chip 
            key={`auto-${q}`} 
            active={s.subQuestions.includes(q)} 
            onClick={() => s.set({ 
              subQuestions: s.subQuestions.includes(q) 
                ? s.subQuestions.filter(x=>x!==q) 
                : s.subQuestions.length >= 3 
                  ? s.subQuestions 
                  : [...s.subQuestions, q]
            })}
          >
            {q}
          </Chip>
        ))}
        
        {/* Show manually added sub-questions that aren't in auto-generated suggestions */}
        {s.subQuestions
          .filter(q => !s.autoGeneratedSuggestions.includes(q))
          .map((q) => (
            <Chip 
              key={`manual-${q}`} 
              active={true} 
              onClick={() => s.set({ 
                subQuestions: s.subQuestions.filter(x=>x!==q) 
              })}
            >
              {q}
            </Chip>
          ))
        }
        
        {/* Show message when no suggestions and not generating */}
        {s.autoGeneratedSuggestions.length === 0 && !s.isGeneratingSubQuestions && (
          <div className="text-gray-500 text-sm">
            No AI suggestions available - add your own sub-questions below
          </div>
        )}
        
        {/* Show generating message */}
        {s.isGeneratingSubQuestions && (
          <div className="text-gray-500 text-sm">
            Generating suggestions...
          </div>
        )}
      </div>
      <div className="flex gap-3 max-w-2xl mx-auto">
        <Input value={val} placeholder="Add your own sub-question" onChange={(e)=>setVal(e.target.value)} />
        <Button onClick={() => { if(!val.trim() || s.subQuestions.length >= 3) return; s.set({ subQuestions: [...s.subQuestions, val.trim()] }); setVal(""); }}>+ Add</Button>
      </div>
    </div>
  );
}

function StepSourcesAccess() {
  const s = useChat();
  const toggleAccess = (k: keyof Access) => s.set({ access: { ...s.access, [k]: !s.access[k] } });
  return (
    <div className="space-y-6">
      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Which sources should we include?</h2>
      </div>
      <div className="flex flex-wrap gap-3 justify-center">
        <Chip active={s.access.academic} onClick={() => toggleAccess("academic")}>Academic (OpenAlex)</Chip>
        <Chip active={s.access.policy} onClick={() => toggleAccess("policy")}>Policy (think tanks and government)</Chip>
      </div>
    </div>
  );
}

function StepTime() {
  const s = useChat();
  return (
    <div className="space-y-6">
      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Time window</h2>
      </div>
      <div className="flex flex-wrap gap-3 justify-center">
        {["LAST_YEAR", "LAST_5_YEARS", "SINCE_2000", "ANY", "CUSTOM"].map((p) => (
          <Chip key={p} active={s.timePreset === p} onClick={() => s.set({ timePreset: p as TimePreset })}>{p.replaceAll("_"," ")}</Chip>
        ))}
      </div>
      {s.timePreset === "CUSTOM" && (
        <div className="flex gap-3 max-w-lg mx-auto">
          <div className="flex-1">
            <div className="text-xs text-gray-500 mb-2">From</div>
            <Input type="date" onChange={(e)=>s.set({ customFrom: e.target.value })} />
          </div>
          <div className="flex-1">
            <div className="text-xs text-gray-500 mb-2">To</div>
            <Input type="date" onChange={(e)=>s.set({ customTo: e.target.value })} />
          </div>
        </div>
      )}
    </div>
  );
}

function StepGeography() {
  const s = useChat();
  const [selectedCountry, setSelectedCountry] = React.useState("");
  const addGeo = (g: string) => s.set({ geography: [...new Set([...s.geography, g])] });
  const removeGeo = (g: string) => s.set({ geography: s.geography.filter(x => x !== g) });
  
  return (
    <div className="space-y-6">
      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Geography</h2>
        <p className="text-gray-600 text-lg">Select one or more regions or countries to focus your search.</p>
      </div>
      
      {/* Quick access chips */}
      <div className="flex flex-wrap gap-3 justify-center">
        {COUNTRIES.map((c) => (
          <Chip key={c} active={s.geography.includes(c)} onClick={() => s.set({ geography: s.geography.includes(c) ? s.geography.filter(x=>x!==c) : [...s.geography, c] })}>{c}</Chip>
        ))}
      </div>
      
      {/* Country/region dropdown */}
      <div className="flex gap-3 max-w-2xl mx-auto">
        <select 
          className="flex-1 px-3 py-2 border border-gray-300 rounded-xl text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-blue-600"
          value={selectedCountry} 
          onChange={(e) => setSelectedCountry(e.target.value)}
        >
          <option value="">Select a country or region</option>
          
          {/* Special regions section */}
          <optgroup label="Regions & Groups">
            {SPECIAL_REGIONS.map((region) => (
              <option key={region} value={region}>{region}</option>
            ))}
          </optgroup>
          
          {/* Individual countries section */}
          <optgroup label="Countries">
            {COUNTRY_LIST.sort().map((country) => (
              <option key={country} value={country}>{country}</option>
            ))}
          </optgroup>
        </select>
        <Button onClick={() => { if(!selectedCountry) return; addGeo(selectedCountry); setSelectedCountry(""); }}>+ Add</Button>
      </div>
      
      {/* Selected geography tags */}
      {s.geography.length > 0 && (
        <div className="space-y-3 max-w-2xl mx-auto">
          <div className="text-sm font-medium text-gray-700 text-center">Selected:</div>
          <div className="flex flex-wrap gap-2 justify-center">
            {s.geography.map((geo) => (
              <div key={geo} className="inline-flex items-center gap-1 px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm">
                {geo}
                <button 
                  onClick={() => removeGeo(geo)}
                  className="ml-1 text-blue-600 hover:text-blue-800"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StepFocus() {
  const s = useChat();
  const [val, setVal] = React.useState("");
  return (
    <div className="space-y-6">
      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">What should the search focus on?</h2>
        <p className="text-gray-600 text-lg">Select the aspects you want included.</p>
      </div>
      {Object.entries(SCOPE_CHIPS).map(([group, chips]) => (
        <div key={group} className="space-y-3">
          <div className="font-medium text-gray-900 text-center">{group}</div>
          <div className="flex flex-wrap gap-3 justify-center">
            {chips.map((c) => (
              <Chip key={c} active={s.scope.includes(c)} onClick={() => s.set({ scope: s.scope.includes(c) ? s.scope.filter(x=>x!==c) : [...s.scope, c] })}>{c}</Chip>
            ))}
          </div>
        </div>
      ))}
      <div className="flex gap-3 max-w-2xl mx-auto">
        <Input value={val} placeholder="Add your own focus" onChange={(e)=>setVal(e.target.value)} />
        <Button onClick={() => { if(!val.trim()) return; s.set({ customFocus: [...s.customFocus, val.trim()] }); setVal(""); }}>+ Add</Button>
      </div>
    </div>
  );
}

function StepExclude() {
  const s = useChat();
  const [val, setVal] = React.useState("");
  return (
    <div className="space-y-6">
      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Anything to exclude?</h2>
        <p className="text-gray-600 text-lg">Choose what you don&apos;t want in your results.</p>
      </div>
      <div className="flex flex-wrap gap-3 justify-center">
        {EXCLUDE_CHIPS.map((c) => (
          <Chip key={c} active={s.excludes.includes(c)} onClick={() => s.set({ excludes: s.excludes.includes(c) ? s.excludes.filter(x=>x!==c) : [...s.excludes, c] })}>{c}</Chip>
        ))}
      </div>
      <div className="flex gap-3 max-w-2xl mx-auto">
        <Input value={val} placeholder="Add your own exclusion" onChange={(e)=>setVal(e.target.value)} />
        <Button onClick={() => { if(!val.trim()) return; s.set({ customExcludes: [...(s.customExcludes||[]), val.trim()] }); setVal(""); }}>+ Add</Button>
      </div>
    </div>
  );
}

function WizardShell({ children }: React.PropsWithChildren) {
  const s = useChat();
  const steps = ["Sub‑questions","Sources","Time","Geography","Focus","Exclude"];

  return (
    <div className="space-y-8">
      <ProgressBar step={s.refineStep} total={steps.length} />
      <div className="flex justify-between items-center py-4">
        <Button variant="secondary" onClick={() => (s.refineStep === 0 ? s.back() : s.backRefine())}>Back</Button>
        <div className="flex gap-3 items-center">
          {s.refineStep < steps.length - 1 ? (
            <Button onClick={() => s.nextRefine()}>Next</Button>
          ) : (
            <Button onClick={() => s.next()}>Review search plan</Button>
          )}
        </div>
      </div>
      <div>{children}</div>
      <div className="text-center pt-2">
        <button 
          className="text-sm text-gray-700 bg-gray-100 hover:bg-gray-200 px-4 py-2 rounded-lg transition-colors border-0" 
          onClick={() => s.set({ showPlan: !s.showPlan })}
        >
          {s.showPlan ? 'Hide search plan ▾' : 'Show search plan ▸'}
        </button>
      </div>
      {s.showPlan && <PlanDrawer />}
    </div>
  );
}


function ScreenRefine() {
  const s = useChat();
  return (
    <div className="mx-auto max-w-4xl px-8 py-16">
      <WizardShell>
        {s.refineStep === 0 && <StepSubQuestions />}
        {s.refineStep === 1 && <StepSourcesAccess />}
        {s.refineStep === 2 && <StepTime />}
        {s.refineStep === 3 && <StepGeography />}
        {s.refineStep === 4 && <StepFocus />}
        {s.refineStep === 5 && <StepExclude />}
      </WizardShell>
    </div>
  );
}


function ScreenApprove({ onRunAnalysis, isRunning = false }: { onRunAnalysis: (brief: Brief) => void; isRunning?: boolean }) {
  const s = useChat();
  
  
  const brief = buildPlan({
    researchQuestion: s.researchQuestion,
    subQuestions: s.subQuestions,
    timePreset: s.timePreset,
    customFrom: s.customFrom,
    customTo: s.customTo,
    geography: s.geography,
    access: s.access,
    scope: s.scope,
    customFocus: s.customFocus,
    excludes: s.excludes,
    customExcludes: s.customExcludes,
    editableQuery: s.editableQuery,
    maxResults: s.maxResults,
  });

  // Build a more comprehensive summary that reflects the actual search scope
  let searchDescription = `"${brief.researchQuestion}"`;
  
  // Add sub-questions in a more natural way
  if (brief.subQuestions.length > 0) {
    if (brief.subQuestions.length === 1) {
      searchDescription += ` and related topics including "${brief.subQuestions[0]}"`;
    } else {
      searchDescription += ` and ${brief.subQuestions.length} related aspects`;
    }
  }
  
  const focusTerms = brief.soft.include.length > 0 ? `, with focus on ${brief.soft.include.join(", ").toLowerCase()}` : "";
  
  const parts: string[] = [];
  if (brief.direct.geography?.length) parts.push(`${brief.direct.geography.join(", ")}`);
  if (brief.direct.timePreset && brief.direct.timePreset !== "ANY") parts.push(brief.direct.timePreset.replaceAll("_"," ").toLowerCase());
  const where = parts.length ? `, focusing on ${parts.join(" and ")}` : "";
  
  const accessArr = [brief.direct.access.academic && "academic", brief.direct.access.policy && "policy"].filter(Boolean) as string[];
  const accessText = accessArr.length ? ` across ${accessArr.join(" and ")} sources` : "";
  
  const exclude = brief.soft.exclude.length ? ` Excluding ${brief.soft.exclude.join(", ").toLowerCase()}.` : "";
  
  const summary = `We'll search for evidence on ${searchDescription}${focusTerms}${where}${accessText}.` + exclude;

  const [showQuery, setShowQuery] = React.useState(false);

  return (
    <div className="mx-auto max-w-3xl px-4 py-12 space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Review your search plan</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">

        <section className="space-y-2">
            <h4 className="font-semibold">Summary</h4>
            <p className="text-base leading-7 text-gray-800">{summary}</p>
          </section>
                    
          <section className="space-y-2">
            <h4 className="font-semibold">Research questions</h4>
            <div className="rounded-xl bg-gray-50 p-4 ring-1 ring-gray-200">
              <div className="mb-3 text-gray-900 font-medium">{brief.researchQuestion || "—"}</div>
              {brief.subQuestions?.length ? (
                <ul className="list-disc pl-6 text-gray-800 space-y-1">
                  {brief.subQuestions.map((q, i) => (<li key={i}>{q}</li>))}
                </ul>
              ) : null}
            </div>
          </section>



          <section className="space-y-2">
            <h4 className="font-semibold cursor-pointer hover:text-gray-700 transition-colors" onClick={() => setShowQuery((v)=>!v)}>
              {showQuery ? 'Hide exact search query ▾' : 'Show exact search query ▸'}
            </h4>
            {showQuery && (
              <div className="space-y-2">
                <div className="relative">
                  <pre className="whitespace-pre-wrap bg-gray-50 ring-1 ring-gray-200 p-3 rounded-xl text-sm pr-16">{brief.direct.query}</pre>
                  <button
                    className="absolute top-2 right-2 text-xs px-2 py-1 rounded-lg ring-1 ring-gray-300 hover:bg-gray-100"
                    onClick={() => navigator.clipboard?.writeText(brief.direct.query)}
                  >Copy</button>
                </div>
                <p className="text-xs text-gray-500">We will adjust the query further for OpenAlex searches to increase the number of results</p>
              </div>
            )}
          </section>


          <section className="space-y-2">
            <h4 className="font-semibold">Details</h4>
            <div className="grid grid-cols-2 gap-3 text-sm text-gray-800">
              <div><span className="font-medium">Time</span><br />{(brief.direct.timePreset||"ANY").replaceAll("_"," ")}</div>
              <div><span className="font-medium">Geography</span><br />{brief.direct.geography?.join(", ") || "—"}</div>
              <div><span className="font-medium">Sources</span><br />{brief.direct.sources.join(", ")}</div>
              <div><span className="font-medium">Access</span><br />{accessArr.join(", ") || "—"}</div>
              <div><span className="font-medium">Include</span><br />{brief.soft.include.join(", ") || "—"}</div>
              <div><span className="font-medium">Exclude</span><br />{brief.soft.exclude.join(", ") || "—"}</div>
              <div>
                <span className="font-medium">Max results</span><br />
                <div className="inline-flex items-center gap-2 mt-1">
                  <button
                    className="px-2 py-1 rounded-lg ring-1 ring-gray-300 hover:bg-gray-50"
                    onClick={() => s.set({ maxResults: Math.max(5, s.maxResults - 5) })}
                    aria-label="Decrease results"
                  >–</button>
                  <span className="min-w-[2ch] text-center">{s.maxResults}</span>
                  <button
                    className="px-2 py-1 rounded-lg ring-1 ring-gray-300 hover:bg-gray-50"
                    onClick={() => s.set({ maxResults: Math.min(200, s.maxResults + 5) })}
                    aria-label="Increase results"
                  >+</button>
                </div>
              </div>
            </div>
          </section>
        </CardContent>
      </Card>
      <div className="flex gap-3">
        <Button variant="secondary" onClick={() => s.back()} disabled={isRunning}>Back</Button>
        <Button onClick={() => onRunAnalysis(brief)} disabled={isRunning}>
          {isRunning ? 'Starting up...' : 'Run Analysis'}
        </Button>
      </div>
    </div>
  );
}

// ---------------- ROOT ----------------
interface ChatInterfaceProps {
  onRunAnalysis: (brief: Brief) => void;
  isRunning?: boolean;
}

export default function ChatInterface({ onRunAnalysis, isRunning = false }: ChatInterfaceProps) {
  const s = useChat();
  return (
    <div className="min-h-screen bg-white text-gray-900">
      {s.step === "ASK" && <ScreenAsk />}
      {s.step === "REFINE" && <ScreenRefine />}
      {s.step === "APPROVE" && <ScreenApprove onRunAnalysis={onRunAnalysis} isRunning={isRunning} />}
    </div>
  );
}