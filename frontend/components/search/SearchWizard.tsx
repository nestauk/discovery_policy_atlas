"use client";

import React, { useState } from "react";
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
type Step = "ASK" | "POPULATION" | "INNER_SETTING" | "OUTCOME" | "PARAMETERS" | "SCREENING" | "ADDITIONAL_QUESTIONS" | "SUMMARY";
type TimePreset = "LAST_YEAR" | "LAST_2_YEARS" | "LAST_5_YEARS" | "LAST_10_YEARS" | "SINCE_2000" | "ANY" | "CUSTOM";
type Access = { academic: boolean; policy: boolean };
const TIME_PRESET_LABELS: Record<TimePreset, string> = {
  LAST_YEAR: "Last year",
  LAST_2_YEARS: "Last 2 years",
  LAST_5_YEARS: "Last 5 years",
  LAST_10_YEARS: "Last 10 years",
  SINCE_2000: "Since 2000",
  ANY: "Any time",
  CUSTOM: "Custom range",
};
const SOURCE_LABELS: Record<"openalex" | "overton", string> = {
  openalex: "Academic literature",
  overton: "Grey literature",
};

// Fallback population examples (used if LLM generation fails)
const FALLBACK_POPULATION_EXAMPLES = [
  "General population",
  "Adults",
  "Children"
] as const;

// Fallback outcome examples (used if LLM generation fails)
const FALLBACK_OUTCOME_EXAMPLES = [
  "Social well-being",
  "Better health outcomes",
  "Improved outcomes"
] as const;

const FALLBACK_INNER_SETTING_EXAMPLES = [
  "Schools",
  "Healthcare facilities",
  "Community centres",
  "Workplaces",
  "Online or digital platforms"
] as const;


// Geography constants
const SPECIAL_REGIONS = [
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

const ANYWHERE_VALUE = "All";
const ANYWHERE_LABEL = "Anywhere";
const GEO_LABELS: Record<string, string> = {
  [ANYWHERE_VALUE]: ANYWHERE_LABEL,
  "All but UK": "Anywhere but UK",
};

// Search context type - stores all the structured data
export type SearchContext = {
  researchQuestion: string;
  population: {
    selected: string[]; // Selected population options (examples + custom)
    keepBroad: boolean; // "Keep it broad" option
  };
  innerSetting: string[];
  outcome: {
    selected: string[]; // Selected outcome options (examples + custom)
    keepBroad: boolean; // "Keep it broad" option
  };
  implementationConstraints: {
    cost: string;
    staffing: string;
    implementationComplexity: string;
  };
  parameters: {
    sources: ("openalex" | "overton")[];
    access: Access;
    geography: string[];
    timePreset: TimePreset;
    customFrom?: string;
    customTo?: string;
  };
  screeningFactors: string[]; // Free text factors for screening
  additionalQuestions: string[]; // Additional research questions
  maxResults: number;
};

// ---------------- STATE ----------------
interface WizardState {
  step: Step;
  researchQuestion: string;
  population: { selected: string[]; keepBroad: boolean };
  innerSetting: { selected: string[]; noPreference: boolean };
  outcome: { selected: string[]; keepBroad: boolean };
  implementationConstraints: {
    cost: string;
    staffing: string;
    implementationComplexity: string;
  };
  generatedPopulationOptions: string[];
  generatedInnerSettingOptions: string[];
  generatedOutcomeOptions: string[];
  generatedAdditionalQuestions: string[];
  isGeneratingOptions: boolean;
  parameters: {
    sources: ("openalex" | "overton")[];
    access: Access;
    geography: string[];
    timePreset: TimePreset;
    customFrom?: string;
    customTo?: string;
  };
  screeningFactors: string[];
  additionalQuestions: string[];
  maxResults: number;
  set: (p: Partial<WizardState>) => void;
  reset: () => void;
  next: () => void;
  back: () => void;
  buildContext: () => SearchContext;
}

export const useWizard = create<WizardState>((set, get) => ({
  step: "ASK",
  researchQuestion: "",
  population: { selected: ["Anyone"], keepBroad: false },
  innerSetting: { selected: [], noPreference: true },
  outcome: { selected: ["I don't have a particular outcome in mind"], keepBroad: false },
  implementationConstraints: {
    cost: "Any",
    staffing: "Any",
    implementationComplexity: "Any",
  },
  generatedPopulationOptions: [],
  generatedInnerSettingOptions: [],
  generatedOutcomeOptions: [],
  generatedAdditionalQuestions: [],
  isGeneratingOptions: false,
  parameters: {
    sources: [],
    access: { academic: true, policy: true },
    geography: [ANYWHERE_VALUE],
    timePreset: "LAST_10_YEARS",
    customFrom: undefined,
    customTo: undefined,
  },
  screeningFactors: [],
  additionalQuestions: [],
  maxResults: 30,
  set: (p) => set(p),
  reset: () =>
    set({
      step: "ASK",
      researchQuestion: "",
      population: { selected: ["Anyone"], keepBroad: false },
      innerSetting: { selected: [], noPreference: true },
      outcome: { selected: ["I don't have a particular outcome in mind"], keepBroad: false },
      implementationConstraints: {
        cost: "Any",
        staffing: "Any",
        implementationComplexity: "Any",
      },
      generatedPopulationOptions: [],
      generatedInnerSettingOptions: [],
      generatedOutcomeOptions: [],
      generatedAdditionalQuestions: [],
      isGeneratingOptions: false,
      parameters: {
        sources: [],
        access: { academic: true, policy: true },
        geography: [ANYWHERE_VALUE],
        timePreset: "LAST_10_YEARS",
        customFrom: undefined,
        customTo: undefined,
      },
      screeningFactors: [],
      additionalQuestions: [],
      maxResults: 30,
    }),
  next: () => {
    const s = get();
    // Skip ADDITIONAL_QUESTIONS step - go directly from SCREENING to SUMMARY
    const steps: Step[] = ["ASK", "POPULATION", "INNER_SETTING", "OUTCOME", "PARAMETERS", "SCREENING", "ADDITIONAL_QUESTIONS", "SUMMARY"];
    const currentIdx = steps.indexOf(s.step);
    if (currentIdx < steps.length - 1) {
      const nextStep = steps[currentIdx + 1];
      // Skip ADDITIONAL_QUESTIONS - go directly to SUMMARY
      if (nextStep === "ADDITIONAL_QUESTIONS") {
        set({ step: "SUMMARY" });
      } else {
        set({ step: nextStep });
      }
    }
  },
  back: () => {
    const s = get();
    // Skip ADDITIONAL_QUESTIONS step - go directly from SUMMARY to SCREENING
    const steps: Step[] = ["ASK", "POPULATION", "INNER_SETTING", "OUTCOME", "PARAMETERS", "SCREENING", "ADDITIONAL_QUESTIONS", "SUMMARY"];
    const currentIdx = steps.indexOf(s.step);
    if (currentIdx > 0) {
      const prevStep = steps[currentIdx - 1];
      // Skip ADDITIONAL_QUESTIONS - go directly to SCREENING
      if (prevStep === "ADDITIONAL_QUESTIONS") {
        set({ step: "SCREENING" });
      } else {
        set({ step: prevStep });
      }
    }
  },
  buildContext: () => {
    const s = get();
    return {
      researchQuestion: s.researchQuestion,
      population: s.population,
      innerSetting: s.innerSetting.noPreference ? [] : s.innerSetting.selected,
      outcome: s.outcome,
      implementationConstraints: s.implementationConstraints,
      parameters: s.parameters,
      screeningFactors: s.screeningFactors,
      additionalQuestions: s.additionalQuestions,
      maxResults: s.maxResults,
    };
  },
}));

// ---------------- HELPERS ----------------
function ProgressBar({ step }: { step: Step }) {
  // Skip ADDITIONAL_QUESTIONS in progress calculation
  const steps: Step[] = ["ASK", "POPULATION", "INNER_SETTING", "OUTCOME", "PARAMETERS", "SCREENING", "SUMMARY"];
  const currentIdx = steps.indexOf(step);
  const pct = Math.round(((currentIdx + 1) / steps.length) * 100);
  return (
    <div className="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
      <div className="h-full bg-blue-600 transition-all" style={{ width: `${pct}%` }} />
    </div>
  );
}

function generateImpliedResearchQuestion(context: SearchContext): string {
  const parts: string[] = [];
  
  // Start with base question
  if (context.researchQuestion) {
    parts.push(context.researchQuestion);
  } else {
    parts.push("What interventions");
  }
  
  // Add population context
  if (context.population.selected.length > 0) {
    const popText = context.population.selected.length === 1 
      ? context.population.selected[0]
      : context.population.selected.join(", ");
    parts.push(`for ${popText}`);
  }
  
  // Add outcome context
  if (context.outcome.selected.length > 0) {
    const outcomeText = context.outcome.selected.length === 1
      ? context.outcome.selected[0]
      : context.outcome.selected.join(", ");
    parts.push(`could achieve ${outcomeText}`);
  }
  
  // If we have a base question, return it; otherwise construct from parts
  if (context.researchQuestion) {
    return context.researchQuestion;
  }
  
  return parts.join(" ") + "?";
}

// ---------------- SCREENS ----------------
function ScreenAsk() {
  const s = useWizard();
  const { generatePopulationOptions, generateOutcomeOptions, generateInnerSettingOptions } = useAPI();

  const handleNext = async () => {
    const researchQuestion = s.researchQuestion.trim();
    if (!researchQuestion) return;

    // Generate population and outcome options
    s.set({ isGeneratingOptions: true });
    
    try {
      // Generate both in parallel
      const [populationResponse, outcomeResponse, innerSettingResponse] = await Promise.all([
        generatePopulationOptions(researchQuestion).catch(() => ({ population_options: [] })),
        generateOutcomeOptions(researchQuestion).catch(() => ({ outcome_options: [] })),
        generateInnerSettingOptions(researchQuestion).catch(() => ({ inner_setting_options: [] })),
      ]);

      s.set({ 
        generatedPopulationOptions: populationResponse?.population_options || [],
        generatedOutcomeOptions: outcomeResponse?.outcome_options || [],
        generatedInnerSettingOptions: innerSettingResponse?.inner_setting_options || [],
        step: "POPULATION"
      });
    } catch (error) {
      console.error('Failed to generate options:', error);
      // Continue with empty options if generation fails
      s.set({ 
        generatedPopulationOptions: [],
        generatedOutcomeOptions: [],
        generatedInnerSettingOptions: [],
        step: "POPULATION" 
      });
    } finally {
      s.set({ isGeneratingOptions: false });
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8 pt-32">
      <div className="text-center space-y-4">
        <div className="flex items-center justify-center gap-3">
          <h1 className="text-4xl font-bold tracking-tight">Find evidence on policy interventions</h1>
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

      <div className="space-y-6">
        <Textarea 
          autoFocus 
          placeholder="Example: Interventions to improve home learning environment for young children" 
          value={s.researchQuestion} 
          onChange={(e) => s.set({ researchQuestion: e.target.value })} 
        />
        <div className="flex justify-end items-center">
          <Button 
            variant="secondary"
            className="!bg-[#A5D6E1] !text-black hover:!bg-[#93c9d6] border-0 ring-0"
            full 
            disabled={!s.researchQuestion.trim() || s.isGeneratingOptions} 
            onClick={handleNext}
          >
            {s.isGeneratingOptions ? 'Generating options...' : 'Continue'}
          </Button>
        </div>
      </div>
    </div>
  );
}

function ScreenPopulation() {
  const s = useWizard();
  const [customInput, setCustomInput] = useState("");
  const ANYONE_OPTION = "Anyone";

  const togglePopulation = (pop: string) => {
    const current = s.population.selected;
    // "Anyone" behaves as a mutually exclusive option.
    if (pop === ANYONE_OPTION) {
      if (current.includes(ANYONE_OPTION)) {
        s.set({ population: { ...s.population, selected: [] } });
      } else {
        s.set({ population: { ...s.population, selected: [ANYONE_OPTION] } });
      }
      return;
    }

    if (current.includes(pop)) {
      const next = current.filter(p => p !== pop);
      s.set({
        population: {
          ...s.population,
          selected: next.length > 0 ? next : [ANYONE_OPTION],
        },
      });
    } else {
      const withoutAnyone = current.filter(p => p !== ANYONE_OPTION);
      s.set({ population: { ...s.population, selected: [...withoutAnyone, pop] } });
    }
  };

  const addCustom = () => {
    const trimmed = customInput.trim();
    // Use generated options or fallback to defaults
    const exampleOptions = s.generatedPopulationOptions.length > 0
      ? [ANYONE_OPTION, ...s.generatedPopulationOptions] as string[]
      : [ANYONE_OPTION, ...FALLBACK_POPULATION_EXAMPLES] as string[];
    if (trimmed && !s.population.selected.includes(trimmed) && !exampleOptions.includes(trimmed)) {
      const withoutAnyone = s.population.selected.filter((p) => p !== ANYONE_OPTION);
      s.set({ population: { ...s.population, selected: [...withoutAnyone, trimmed] } });
      setCustomInput("");
    }
  };

  const removePopulation = (pop: string) => {
    const next = s.population.selected.filter(p => p !== pop);
    s.set({
      population: {
        ...s.population,
        selected: next.length > 0 ? next : [ANYONE_OPTION],
      },
    });
  };

  // Use generated options or fallback to defaults
  const exampleOptions = s.generatedPopulationOptions.length > 0
    ? [ANYONE_OPTION, ...s.generatedPopulationOptions] as string[]
    : [ANYONE_OPTION, ...FALLBACK_POPULATION_EXAMPLES] as string[];
  const customOptions = s.population.selected.filter(pop => !exampleOptions.includes(pop));

  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8 py-16">
      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Are you targeting a particular population?</h2>
        <p className="text-gray-600 text-lg">We will use this to filter only the most relevant information</p>
      </div>

      <div className="space-y-6 max-w-2xl mx-auto">
        {/* Options in single column */}
        <div className="flex flex-col gap-3">
          {exampleOptions.slice(0, 1).map((pop) => {
            const isSelected = s.population.selected.includes(pop);
            return (
              <button
                key={pop}
                type="button"
                onClick={() => togglePopulation(pop)}
                className={cx(
                  "w-full text-left px-4 py-4 rounded-xl transition ring-1 whitespace-normal break-words",
                  isSelected
                    ? "bg-blue-600 !text-white ring-blue-600"
                    : "bg-white text-gray-900 ring-gray-300 hover:bg-gray-50"
                )}
              >
                {pop}
              </button>
            );
          })}

          <div className="flex items-center gap-3 py-1">
            <div className="h-px flex-1 bg-gray-200" />
            <span className="text-xs text-gray-500 uppercase tracking-wide">Or select specific populations</span>
            <div className="h-px flex-1 bg-gray-200" />
          </div>

          {exampleOptions.slice(1).map((pop) => {
            const isSelected = s.population.selected.includes(pop);
            return (
              <button
                key={pop}
                type="button"
                onClick={() => togglePopulation(pop)}
                className={cx(
                  "w-full text-left px-4 py-4 rounded-xl transition ring-1 whitespace-normal break-words",
                  isSelected
                    ? "bg-blue-600 !text-white ring-blue-600"
                    : "bg-white text-gray-900 ring-gray-300 hover:bg-gray-50"
                )}
              >
                {pop}
              </button>
            );
          })}
          
          {/* Custom added options */}
          {customOptions.map((pop) => (
            <div
              key={pop}
              className="w-full text-left px-4 py-4 rounded-xl bg-blue-600 !text-white ring-1 ring-blue-600 flex items-center justify-between whitespace-normal break-words"
            >
              <span>{pop}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  removePopulation(pop);
                }}
                className="ml-2 text-white hover:text-blue-100"
                aria-label="Remove"
              >
                ×
              </button>
            </div>
          ))}
        </div>

        {/* Custom input */}
        <div className="flex gap-3">
          <Input
            value={customInput}
            placeholder="Add your own population"
            onChange={(e) => setCustomInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addCustom()}
          />
          <Button onClick={addCustom}>+ Add</Button>
        </div>
      </div>

      <div className="flex justify-between items-center rounded-2xl border border-gray-200 bg-gray-50 p-4">
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => s.back()}>Back</Button>
          <Button variant="secondary" onClick={() => s.reset()}>Restart</Button>
        </div>
        <Button variant="secondary" className="!bg-[#A5D6E1] !text-black hover:!bg-[#93c9d6] border-0 ring-0" onClick={() => s.next()}>Next</Button>
      </div>
    </div>
  );
}

function ScreenInnerSetting() {
  const s = useWizard();
  const [customInput, setCustomInput] = useState("");

  const toggleSetting = (setting: string) => {
    const current = s.innerSetting.selected;
    if (s.innerSetting.noPreference) {
      s.set({ innerSetting: { selected: [setting], noPreference: false } });
      return;
    }
    if (current.includes(setting)) {
      const next = current.filter((item) => item !== setting);
      s.set({
        innerSetting: {
          selected: next,
          noPreference: next.length === 0,
        },
      });
    } else {
      s.set({
        innerSetting: {
          selected: [...current, setting],
          noPreference: false,
        },
      });
    }
  };

  const selectNoPreference = () => {
    s.set({ innerSetting: { selected: [], noPreference: true } });
  };

  const addCustom = () => {
    const trimmed = customInput.trim();
    if (!trimmed) return;
    if (!s.innerSetting.selected.includes(trimmed)) {
      s.set({
        innerSetting: {
          selected: [...s.innerSetting.selected, trimmed],
          noPreference: false,
        },
      });
    }
    setCustomInput("");
  };

  const removeCustom = (setting: string) => {
    const next = s.innerSetting.selected.filter((item) => item !== setting);
    s.set({
      innerSetting: {
        selected: next,
        noPreference: next.length === 0,
      },
    });
  };

  const exampleOptions = s.generatedInnerSettingOptions.length > 0
    ? s.generatedInnerSettingOptions
    : [...FALLBACK_INNER_SETTING_EXAMPLES];
  const customOptions = s.innerSetting.selected.filter(
    (setting) => !exampleOptions.includes(setting)
  );

  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8 py-16">
      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Are you interested in particular settings?</h2>
        <p className="text-gray-600 text-lg">We will use this to filter only the most relevant information and assess transferability.</p>
      </div>

      <div className="space-y-6 max-w-2xl mx-auto">
        <div className="flex flex-col gap-3">
          <button
            type="button"
            onClick={selectNoPreference}
            className={cx(
              "w-full text-left px-4 py-4 rounded-xl transition ring-1 whitespace-normal break-words",
              s.innerSetting.noPreference
                ? "bg-blue-600 !text-white ring-blue-600"
                : "bg-white text-gray-900 ring-gray-300 hover:bg-gray-50"
            )}
          >
            No preference
          </button>

          <div className="flex items-center gap-3 py-1">
            <div className="h-px flex-1 bg-gray-200" />
            <span className="text-xs text-gray-500 uppercase tracking-wide">Or select specific settings</span>
            <div className="h-px flex-1 bg-gray-200" />
          </div>

          {exampleOptions.map((setting) => {
            const isSelected = s.innerSetting.selected.includes(setting);
            return (
              <button
                key={setting}
                type="button"
                onClick={() => toggleSetting(setting)}
                className={cx(
                  "w-full text-left px-4 py-4 rounded-xl transition ring-1 whitespace-normal break-words",
                  isSelected
                    ? "bg-blue-600 !text-white ring-blue-600"
                    : "bg-white text-gray-900 ring-gray-300 hover:bg-gray-50"
                )}
              >
                {setting}
              </button>
            );
          })}

          {customOptions.map((setting) => (
            <div
              key={setting}
              role="group"
              className="w-full text-left px-4 py-4 rounded-xl bg-blue-600 !text-white ring-1 ring-blue-600 flex items-center justify-between whitespace-normal break-words"
            >
              <span>{setting}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  removeCustom(setting);
                }}
                className="ml-2 text-white hover:text-blue-100"
                aria-label="Remove"
                type="button"
              >
                ×
              </button>
            </div>
          ))}
        </div>

        <div className="flex gap-3">
          <Input
            value={customInput}
            placeholder="Add a custom setting"
            onChange={(e) => setCustomInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addCustom()}
          />
          <Button onClick={addCustom}>+ Add</Button>
        </div>
      </div>

      <div className="flex justify-between items-center rounded-2xl border border-gray-200 bg-gray-50 p-4">
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => s.back()}>Back</Button>
          <Button variant="secondary" onClick={() => s.reset()}>Restart</Button>
        </div>
        <Button variant="secondary" className="!bg-[#A5D6E1] !text-black hover:!bg-[#93c9d6] border-0 ring-0" onClick={() => s.next()}>Next</Button>
      </div>
    </div>
  );
}

function ScreenOutcome() {
  const s = useWizard();
  const [customInput, setCustomInput] = useState("");
  const NO_OUTCOME_OPTION = "I don't have a particular outcome in mind";

  const toggleOutcome = (outcome: string) => {
    const current = s.outcome.selected;
    // "No particular outcome" behaves as a mutually exclusive option.
    if (outcome === NO_OUTCOME_OPTION) {
      if (current.includes(NO_OUTCOME_OPTION)) {
        s.set({ outcome: { ...s.outcome, selected: [] } });
      } else {
        s.set({ outcome: { ...s.outcome, selected: [NO_OUTCOME_OPTION] } });
      }
      return;
    }

    if (current.includes(outcome)) {
      const next = current.filter(o => o !== outcome);
      s.set({
        outcome: {
          ...s.outcome,
          selected: next.length > 0 ? next : [NO_OUTCOME_OPTION],
        },
      });
    } else {
      const withoutNoOutcome = current.filter(o => o !== NO_OUTCOME_OPTION);
      s.set({ outcome: { ...s.outcome, selected: [...withoutNoOutcome, outcome] } });
    }
  };

  const addCustom = () => {
    const trimmed = customInput.trim();
    // Use generated options or fallback to defaults
    const exampleOptions = s.generatedOutcomeOptions.length > 0
      ? [NO_OUTCOME_OPTION, ...s.generatedOutcomeOptions] as string[]
      : [NO_OUTCOME_OPTION, ...FALLBACK_OUTCOME_EXAMPLES] as string[];
    if (trimmed && !s.outcome.selected.includes(trimmed) && !exampleOptions.includes(trimmed)) {
      const withoutNoOutcome = s.outcome.selected.filter(o => o !== NO_OUTCOME_OPTION);
      s.set({ outcome: { ...s.outcome, selected: [...withoutNoOutcome, trimmed] } });
      setCustomInput("");
    }
  };

  const removeOutcome = (outcome: string) => {
    const next = s.outcome.selected.filter(o => o !== outcome);
    s.set({
      outcome: {
        ...s.outcome,
        selected: next.length > 0 ? next : [NO_OUTCOME_OPTION],
      },
    });
  };

  // Use generated options or fallback to defaults
  const exampleOptions = s.generatedOutcomeOptions.length > 0
    ? [NO_OUTCOME_OPTION, ...s.generatedOutcomeOptions] as string[]
    : [NO_OUTCOME_OPTION, ...FALLBACK_OUTCOME_EXAMPLES] as string[];
  const customOptions = s.outcome.selected.filter(outcome => !exampleOptions.includes(outcome));

  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8 py-16">
      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Are you interested in particular outcomes?</h2>
        <p className="text-gray-600 text-lg">We will use this to filter only the most relevant information</p>
      </div>

      <div className="space-y-6 max-w-2xl mx-auto">
        {/* Options in single column */}
        <div className="flex flex-col gap-3">
          {exampleOptions.slice(0, 1).map((outcome) => {
            const isSelected = s.outcome.selected.includes(outcome);
            return (
              <button
                key={outcome}
                type="button"
                onClick={() => toggleOutcome(outcome)}
                className={cx(
                  "w-full text-left px-4 py-4 rounded-xl transition ring-1 whitespace-normal break-words",
                  isSelected
                    ? "bg-blue-600 !text-white ring-blue-600"
                    : "bg-white text-gray-900 ring-gray-300 hover:bg-gray-50"
                )}
              >
                {outcome}
              </button>
            );
          })}

          <div className="flex items-center gap-3 py-1">
            <div className="h-px flex-1 bg-gray-200" />
            <span className="text-xs text-gray-500 uppercase tracking-wide">Or select specific outcomes</span>
            <div className="h-px flex-1 bg-gray-200" />
          </div>

          {exampleOptions.slice(1).map((outcome) => {
            const isSelected = s.outcome.selected.includes(outcome);
            return (
              <button
                key={outcome}
                type="button"
                onClick={() => toggleOutcome(outcome)}
                className={cx(
                  "w-full text-left px-4 py-4 rounded-xl transition ring-1 whitespace-normal break-words",
                  isSelected
                    ? "bg-blue-600 !text-white ring-blue-600"
                    : "bg-white text-gray-900 ring-gray-300 hover:bg-gray-50"
                )}
              >
                {outcome}
              </button>
            );
          })}
          
          {/* Custom added options */}
          {customOptions.map((outcome) => (
            <div
              key={outcome}
              className="w-full text-left px-4 py-4 rounded-xl bg-blue-600 !text-white ring-1 ring-blue-600 flex items-center justify-between whitespace-normal break-words"
            >
              <span>{outcome}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  removeOutcome(outcome);
                }}
                className="ml-2 text-white hover:text-blue-100"
                aria-label="Remove"
              >
                ×
              </button>
            </div>
          ))}
        </div>

        {/* Custom input */}
        <div className="flex gap-3">
          <Input
            value={customInput}
            placeholder="Add your own outcome"
            onChange={(e) => setCustomInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addCustom()}
          />
          <Button onClick={addCustom}>+ Add</Button>
        </div>
      </div>

      <div className="flex justify-between items-center rounded-2xl border border-gray-200 bg-gray-50 p-4">
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => s.back()}>Back</Button>
          <Button variant="secondary" onClick={() => s.reset()}>Restart</Button>
        </div>
        <Button variant="secondary" className="!bg-[#A5D6E1] !text-black hover:!bg-[#93c9d6] border-0 ring-0" onClick={() => s.next()}>Next</Button>
      </div>
    </div>
  );
}

function ScreenParameters() {
  const s = useWizard();
  const [selectedCountry, setSelectedCountry] = useState("");
  const constraintOptions = ["Any", "Low", "Moderate", "High"];

  const toggleAccess = (k: keyof Access) => {
    s.set({ parameters: { ...s.parameters, access: { ...s.parameters.access, [k]: !s.parameters.access[k] } } });
  };

  const addGeo = (g: string) => {
    if (g === ANYWHERE_VALUE) {
      s.set({ parameters: { ...s.parameters, geography: [ANYWHERE_VALUE] } });
      return;
    }

    const existing = s.parameters.geography.filter((x) => x !== ANYWHERE_VALUE);
    if (!existing.includes(g)) {
      s.set({ parameters: { ...s.parameters, geography: [...existing, g] } });
    }
  };

  const removeGeo = (g: string) => {
    s.set({ parameters: { ...s.parameters, geography: s.parameters.geography.filter(x => x !== g) } });
  };

  // Update sources based on access
  React.useEffect(() => {
    const sources: ("openalex" | "overton")[] = [];
    if (s.parameters.access.academic) sources.push("openalex");
    if (s.parameters.access.policy) sources.push("overton");
    s.set({ parameters: { ...s.parameters, sources } });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.parameters.access.academic, s.parameters.access.policy]);

  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8 py-16">
      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Sources, time window, and geography</h2>
        <p className="text-gray-600 text-lg">We will use this filter only the most relevant information</p>
      </div>

      <div className="space-y-8">
        {/* Sources */}
        <div className="space-y-4">
          <h3 className="font-semibold text-lg">Which sources should we use?</h3>
          <div className="flex flex-wrap gap-3">
            <Chip active={s.parameters.access.academic} onClick={() => toggleAccess("academic")}>
              Academic literature
            </Chip>
            <Chip active={s.parameters.access.policy} onClick={() => toggleAccess("policy")}>
              Grey literature (think tanks and governments)
            </Chip>
          </div>
        </div>

        {/* Time window */}
        <div className="space-y-4">
          <h3 className="font-semibold text-lg">When should the evidence be published?</h3>
          <div className="flex flex-wrap gap-3">
            {["LAST_YEAR", "LAST_2_YEARS", "LAST_5_YEARS", "LAST_10_YEARS", "SINCE_2000", "ANY", "CUSTOM"].map((p) => (
              <Chip
                key={p}
                active={s.parameters.timePreset === p}
                onClick={() => s.set({ parameters: { ...s.parameters, timePreset: p as TimePreset } })}
              >
                {TIME_PRESET_LABELS[p as TimePreset]}
              </Chip>
            ))}
          </div>
          {s.parameters.timePreset === "CUSTOM" && (
            <div className="max-w-3xl rounded-2xl border border-blue-100 bg-blue-50/40 p-4 space-y-3">
              <p className="text-sm text-gray-600">Select a start and end date for your custom range.</p>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="flex-1">
                  <div className="text-xs text-gray-500 mb-2">From</div>
                  <Input
                    type="date"
                    value={s.parameters.customFrom || ""}
                    onChange={(e) => s.set({ parameters: { ...s.parameters, customFrom: e.target.value } })}
                  />
                </div>
                <div className="flex-1">
                  <div className="text-xs text-gray-500 mb-2">To</div>
                  <Input
                    type="date"
                    value={s.parameters.customTo || ""}
                    onChange={(e) => s.set({ parameters: { ...s.parameters, customTo: e.target.value } })}
                  />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Geography */}
        <div className="space-y-4 max-w-2xl">
          <h3 className="font-semibold text-lg">In which countries should we look for evidence?</h3>
          <div>
            {/* Selected options */}
            <div className="flex flex-col gap-3">
              {s.parameters.geography.map((geo) => (
                <div
                  key={geo}
                  role="group"
                  className="w-full text-left px-4 py-4 rounded-xl bg-blue-600 !text-white ring-1 ring-blue-600 flex items-center justify-between whitespace-normal break-words"
                >
                  <span>{GEO_LABELS[geo] || geo}</span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      removeGeo(geo);
                    }}
                    className="ml-2 text-white hover:text-blue-100"
                    aria-label="Remove"
                    type="button"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>

            {/* Dropdown input */}
            <div className="flex gap-3 mt-4">
              <select
                className="flex-1 px-3 py-2 border border-gray-300 rounded-xl text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-600"
                value={selectedCountry}
                onChange={(e) => setSelectedCountry(e.target.value)}
              >
                <option value="">{`Select a country or region`}</option>
                <option value={ANYWHERE_VALUE}>{ANYWHERE_LABEL}</option>
                <optgroup label="Regions & Groups">
                  {SPECIAL_REGIONS.map((region) => (
                    <option key={region} value={region}>{GEO_LABELS[region] || region}</option>
                  ))}
                </optgroup>
                <optgroup label="Countries">
                  {COUNTRY_LIST.sort().map((country) => (
                    <option key={country} value={country}>{country}</option>
                  ))}
                </optgroup>
              </select>
              <Button onClick={() => { if (selectedCountry && !s.parameters.geography.includes(selectedCountry)) { addGeo(selectedCountry); setSelectedCountry(""); } }}>
                + Add
              </Button>
            </div>
          </div>
        </div>

        {/* Implementation constraints (optional) */}
        <div className="space-y-4 max-w-2xl">
          <h3 className="font-semibold text-lg">Do you have implementation constraints we should consider?</h3>
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <span>Optional. Leave as “Any” if you do not want to filter by implementation feasibility.</span>
            <Tooltip
              content={
                <div className="max-w-xs text-sm space-y-1">
                  <p><span className="font-medium">Low</span>: minimal resources or operational effort required.</p>
                  <p><span className="font-medium">Moderate</span>: manageable resources and coordination needed.</p>
                  <p><span className="font-medium">High</span>: substantial resources, staffing, or delivery complexity.</p>
                </div>
              }
            >
              <button
                type="button"
                className="inline-flex items-center justify-center h-5 w-5 rounded-full border border-gray-300 text-xs text-gray-600 hover:bg-gray-50"
                aria-label="How level values are interpreted"
              >
                ?
              </button>
            </Tooltip>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-2">
              <div className="text-xs text-gray-500">Cost tolerance</div>
              <select
                className="w-full px-3 py-2 border border-gray-300 rounded-xl text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-600"
                value={s.implementationConstraints.cost}
                onChange={(e) =>
                  s.set({
                    implementationConstraints: {
                      ...s.implementationConstraints,
                      cost: e.target.value,
                    },
                  })
                }
              >
                {constraintOptions.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <div className="text-xs text-gray-500">Staffing capacity</div>
              <select
                className="w-full px-3 py-2 border border-gray-300 rounded-xl text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-600"
                value={s.implementationConstraints.staffing}
                onChange={(e) =>
                  s.set({
                    implementationConstraints: {
                      ...s.implementationConstraints,
                      staffing: e.target.value,
                    },
                  })
                }
              >
                {constraintOptions.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <div className="text-xs text-gray-500">Complexity tolerance</div>
              <select
                className="w-full px-3 py-2 border border-gray-300 rounded-xl text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-600"
                value={s.implementationConstraints.implementationComplexity}
                onChange={(e) =>
                  s.set({
                    implementationConstraints: {
                      ...s.implementationConstraints,
                      implementationComplexity: e.target.value,
                    },
                  })
                }
              >
                {constraintOptions.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

      </div>

      <div className="flex justify-between items-center rounded-2xl border border-gray-200 bg-gray-50 p-4">
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => s.back()}>Back</Button>
          <Button variant="secondary" onClick={() => s.reset()}>Restart</Button>
        </div>
        <Button variant="secondary" className="!bg-[#A5D6E1] !text-black hover:!bg-[#93c9d6] border-0 ring-0" onClick={() => s.next()}>Next</Button>
      </div>
    </div>
  );
}

function ScreenScreening() {
  const s = useWizard();
  const [customInput, setCustomInput] = useState("");

  const addFactor = () => {
    if (customInput.trim() && !s.screeningFactors.includes(customInput.trim())) {
      s.set({ screeningFactors: [...s.screeningFactors, customInput.trim()] });
      setCustomInput("");
    }
  };

  const removeFactor = (factor: string) => {
    s.set({ screeningFactors: s.screeningFactors.filter(f => f !== factor) });
  };

  const handleNext = async () => {
    // Skip ADDITIONAL_QUESTIONS step - go directly to SUMMARY
    // (Keeping generation code commented out for future use)
    // s.set({ isGeneratingOptions: true });
    // 
    // try {
    //   const response = await generateAdditionalQuestions(
    //     s.researchQuestion,
    //     s.population.selected,
    //     s.outcome.selected
    //   ).catch(() => ({ additional_questions: [] }));
    //
    //   const generatedQuestions = response?.additional_questions || [];
    //   
    //   // Preselect generated questions
    //   s.set({ 
    //     generatedAdditionalQuestions: generatedQuestions,
    //     additionalQuestions: generatedQuestions,
    //     step: "ADDITIONAL_QUESTIONS"
    //   });
    // } catch (error) {
    //   console.error('Failed to generate additional questions:', error);
    //   // Continue with empty questions if generation fails
    //   s.set({ 
    //     generatedAdditionalQuestions: [],
    //     step: "ADDITIONAL_QUESTIONS" 
    //   });
    // } finally {
    //   s.set({ isGeneratingOptions: false });
    // }
    
    // Go directly to SUMMARY
    s.set({ step: "SUMMARY" });
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8 py-16">
      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Anything else to consider when screening the evidence?</h2>
        <p className="text-gray-600 text-lg">We will use this to filter only the most relevant information</p>
      </div>

      <div className="space-y-6 max-w-2xl mx-auto">
        {/* Selected factors as buttons */}
        {s.screeningFactors.length > 0 && (
          <div>
            {s.screeningFactors.map((factor) => (
              <div
                key={factor}
                className="w-full text-left px-4 py-4 rounded-xl bg-blue-600 !text-white ring-1 ring-blue-600 flex items-center justify-between mb-3"
              >
                <span>{factor}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    removeFactor(factor);
                  }}
                  className="ml-2 text-white hover:text-blue-100"
                  aria-label="Remove"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Custom input */}
        <div className="flex gap-3">
          <Input
            value={customInput}
            placeholder="Add a screening factor (eg, 'Only studies with children below 5 years old')"
            onChange={(e) => setCustomInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addFactor()}
          />
          <Button onClick={addFactor}>+ Add</Button>
        </div>
      </div>

      <div className="flex justify-between items-center rounded-2xl border border-gray-200 bg-gray-50 p-4">
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => s.back()}>Back</Button>
          <Button variant="secondary" onClick={() => s.reset()}>Restart</Button>
        </div>
        <Button variant="secondary" className="!bg-[#A5D6E1] !text-black hover:!bg-[#93c9d6] border-0 ring-0" onClick={handleNext} disabled={s.isGeneratingOptions}>
          {s.isGeneratingOptions ? "Generating..." : "Next"}
        </Button>
      </div>
    </div>
  );
}

function ScreenAdditionalQuestions() {
  const s = useWizard();
  const [customQuestion, setCustomQuestion] = useState("");

  const addQuestion = () => {
    if (customQuestion.trim() && !s.additionalQuestions.includes(customQuestion.trim())) {
      s.set({ additionalQuestions: [...s.additionalQuestions, customQuestion.trim()] });
      setCustomQuestion("");
    }
  };

  const removeQuestion = (q: string) => {
    s.set({ additionalQuestions: s.additionalQuestions.filter(x => x !== q) });
  };

  const toggleQuestion = (q: string) => {
    if (s.additionalQuestions.includes(q)) {
      removeQuestion(q);
    } else {
      s.set({ additionalQuestions: [...s.additionalQuestions, q] });
    }
  };

  // Combine generated and any custom questions that aren't already selected
  const allAvailableQuestions = [
    ...s.generatedAdditionalQuestions,
    ...s.additionalQuestions.filter((q: string) => !s.generatedAdditionalQuestions.includes(q))
  ];

  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8 py-16">
      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Specific research questions?</h2>
        <p className="text-gray-600 text-lg">We will use these to shape the summary write-up</p>
      </div>

      <div className="space-y-6 max-w-2xl mx-auto">
        {/* Generated and selected questions as buttons */}
        {allAvailableQuestions.length > 0 && (
          <div>
            {allAvailableQuestions.map((q) => {
              const isSelected = s.additionalQuestions.includes(q);
              return (
                <div
                  key={q}
                  onClick={() => toggleQuestion(q)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      toggleQuestion(q);
                    }
                  }}
                  role="button"
                  tabIndex={0}
                  className={cx(
                    "w-full text-left px-4 py-4 rounded-xl flex items-center justify-between mb-3",
                    isSelected
                      ? "bg-blue-600 !text-white ring-1 ring-blue-600"
                      : "bg-white text-gray-900 ring-1 ring-gray-300 hover:bg-gray-50"
                  )}
                >
                  <span>{q}</span>
                  {isSelected && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        removeQuestion(q);
                      }}
                      className="ml-2 text-white hover:text-blue-100"
                      aria-label="Remove"
                    >
                      ×
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Custom question input */}
        <div className="flex gap-3">
          <Input
            value={customQuestion}
            placeholder="Add your own question"
            onChange={(e) => setCustomQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addQuestion()}
          />
          <Button onClick={addQuestion}>+ Add</Button>
        </div>
      </div>

      <div className="flex justify-between items-center rounded-2xl border border-gray-200 bg-gray-50 p-4">
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => s.back()}>Back</Button>
          <Button variant="secondary" onClick={() => s.reset()}>Restart</Button>
        </div>
        <Button variant="secondary" className="!bg-[#A5D6E1] !text-black hover:!bg-[#93c9d6] border-0 ring-0" onClick={() => s.next()}>Next</Button>
      </div>
    </div>
  );
}

function ScreenSummary({ onRunAnalysis, isRunning = false }: { onRunAnalysis: (context: SearchContext) => void; isRunning?: boolean }) {
  const s = useWizard();
  const context = s.buildContext();
  const goToStep = (step: Step) => s.set({ step });
  const impliedQuestion = generateImpliedResearchQuestion(context);
  const hasImplementationConstraints = [
    context.implementationConstraints.cost,
    context.implementationConstraints.staffing,
    context.implementationConstraints.implementationComplexity,
  ].some((value) => value && value !== "Any");
  const hasCustomDateRange =
    context.parameters.timePreset === "CUSTOM" &&
    (context.parameters.customFrom || context.parameters.customTo);
  const timeWindowLabel = TIME_PRESET_LABELS[context.parameters.timePreset];

  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8 py-16">
      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Summary</h2>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Your research question</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-lg text-gray-800">{impliedQuestion}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Search parameters</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-4">
            <button
              type="button"
              onClick={() => goToStep("POPULATION")}
              className="rounded-xl border border-gray-200 bg-gray-50/50 p-4 text-left transition hover:bg-gray-50"
            >
              <div className="text-xs uppercase tracking-wide text-gray-500 mb-1">Population</div>
              {context.population.selected.length > 0 ? (
                <p className="text-gray-900">{context.population.selected.join(", ")}</p>
              ) : (
                <p className="text-gray-500">Not specified</p>
              )}
            </button>
            <button
              type="button"
              onClick={() => goToStep("INNER_SETTING")}
              className="rounded-xl border border-gray-200 bg-gray-50/50 p-4 text-left transition hover:bg-gray-50"
            >
              <div className="text-xs uppercase tracking-wide text-gray-500 mb-1">Setting</div>
              {context.innerSetting.length > 0 ? (
                <p className="text-gray-900">{context.innerSetting.join(", ")}</p>
              ) : (
                <p className="text-gray-500">No preference</p>
              )}
            </button>
            <button
              type="button"
              onClick={() => goToStep("OUTCOME")}
              className="rounded-xl border border-gray-200 bg-gray-50/50 p-4 text-left transition hover:bg-gray-50"
            >
              <div className="text-xs uppercase tracking-wide text-gray-500 mb-1">Outcome</div>
              {context.outcome.selected.length > 0 ? (
                <p className="text-gray-900">{context.outcome.selected.join(", ")}</p>
              ) : (
                <p className="text-gray-500">Not specified</p>
              )}
            </button>
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-4">
            <div className="text-xs uppercase tracking-wide text-gray-500">Filters</div>
            <div className="space-y-3">
              <button type="button" onClick={() => goToStep("PARAMETERS")} className="block w-full text-left rounded-lg p-1 transition hover:bg-gray-50">
                <span className="font-medium">Search sources</span>
                <div className="mt-2 flex flex-wrap gap-2">
                  {context.parameters.sources.length > 0 ? (
                    context.parameters.sources.map((src) => (
                      <span key={src} className="inline-flex items-center rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-800">
                        {SOURCE_LABELS[src] ?? src}
                      </span>
                    ))
                  ) : (
                    <span className="text-gray-500">Not specified</span>
                  )}
                </div>
              </button>
              <button type="button" onClick={() => goToStep("PARAMETERS")} className="block w-full text-left rounded-lg p-1 transition hover:bg-gray-50">
                <span className="font-medium">Time window</span>
                <div className="mt-2 flex flex-wrap gap-2">
                  <span className="inline-flex items-center rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-800">
                    {timeWindowLabel}
                  </span>
                  {hasCustomDateRange && (
                    <span className="inline-flex items-center rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-800">
                      {context.parameters.customFrom || "No start date"} to{" "}
                      {context.parameters.customTo || "No end date"}
                    </span>
                  )}
                </div>
              </button>
              <button type="button" onClick={() => goToStep("PARAMETERS")} className="block w-full text-left rounded-lg p-1 transition hover:bg-gray-50">
                <span className="font-medium">Geography</span>
                <div className="mt-2 flex flex-wrap gap-2">
                  {context.parameters.geography.length > 0 ? (
                    context.parameters.geography.map((geo) => (
                      <span key={geo} className="inline-flex items-center rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-800">
                        {GEO_LABELS[geo] || geo}
                      </span>
                    ))
                  ) : (
                    <span className="text-gray-500">Not specified</span>
                  )}
                </div>
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-3">
            <div className="text-xs uppercase tracking-wide text-gray-500">Prioritisation</div>
            <button type="button" onClick={() => goToStep("PARAMETERS")} className="block w-full text-left rounded-lg p-1 transition hover:bg-gray-50">
              <span className="font-medium">Implementation constraints</span>
              {hasImplementationConstraints ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  <span className="inline-flex items-center rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-800">
                    Cost: {context.implementationConstraints.cost}
                  </span>
                  <span className="inline-flex items-center rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-800">
                    Staffing: {context.implementationConstraints.staffing}
                  </span>
                  <span className="inline-flex items-center rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-800">
                    Complexity: {context.implementationConstraints.implementationComplexity}
                  </span>
                </div>
              ) : (
                <div className="mt-2 text-gray-500">Not specified</div>
              )}
            </button>
            <button type="button" onClick={() => goToStep("SCREENING")} className="block w-full text-left rounded-lg p-1 transition hover:bg-gray-50">
              <span className="font-medium">Screening factors</span>
              {context.screeningFactors.length > 0 ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {context.screeningFactors.map((factor) => (
                    <span key={factor} className="inline-flex items-center rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-800">
                      {factor}
                    </span>
                  ))}
                </div>
              ) : (
                <div className="mt-2 text-gray-500">None added</div>
              )}
            </button>
          </div>

            <div className="rounded-xl border border-blue-200 bg-blue-50/60 p-4">
              <div className="text-xs uppercase tracking-wide text-blue-700 mb-1">Retrieval limit</div>
              <p className="text-sm text-gray-700 mb-3">
                Maximum number of results retrieved from each selected source.
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-medium">Max results per source:</span>
                <div className="inline-flex items-center gap-2">
                  <button
                    type="button"
                    className="px-2 py-1 rounded-lg ring-1 ring-gray-300 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                    onClick={() => s.set({ maxResults: Math.max(5, s.maxResults - 5) })}
                    disabled={isRunning}
                    aria-label="Decrease results"
                  >–</button>
                  <span className="min-w-[2ch] text-center font-semibold">{s.maxResults}</span>
                  <button
                    type="button"
                    className="px-2 py-1 rounded-lg ring-1 ring-gray-300 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                    onClick={() => s.set({ maxResults: Math.min(200, s.maxResults + 5) })}
                    disabled={isRunning}
                    aria-label="Increase results"
                  >+</button>
                </div>
                <span className="text-xs text-gray-500">
                  {context.parameters.sources.length || 0} source{context.parameters.sources.length === 1 ? "" : "s"} selected
                </span>
              </div>
            </div>
        </CardContent>
      </Card>

      <div className="flex justify-between items-center rounded-2xl border border-gray-200 bg-gray-50 p-4">
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => s.back()} disabled={isRunning}>Back</Button>
          <Button variant="secondary" onClick={() => s.reset()} disabled={isRunning}>Start new search</Button>
        </div>
        <Button variant="secondary" className="!bg-[#A5D6E1] !text-black hover:!bg-[#93c9d6] border-0 ring-0" onClick={() => onRunAnalysis(context)} disabled={isRunning}>
          {isRunning ? 'Starting up...' : 'Run Analysis'}
        </Button>
      </div>
    </div>
  );
}


// ---------------- ROOT ----------------
interface SearchWizardProps {
  onRunAnalysis: (context: SearchContext) => void;
  isRunning?: boolean;
}

export default function SearchWizard({ onRunAnalysis, isRunning = false }: SearchWizardProps) {
  const s = useWizard();

  return (
    <div className="min-h-screen bg-white text-gray-900">
      <ProgressBar step={s.step} />
      {s.step === "ASK" && <ScreenAsk />}
      {s.step === "POPULATION" && <ScreenPopulation />}
      {s.step === "INNER_SETTING" && <ScreenInnerSetting />}
      {s.step === "OUTCOME" && <ScreenOutcome />}
      {s.step === "PARAMETERS" && <ScreenParameters />}
      {s.step === "SCREENING" && <ScreenScreening />}
      {s.step === "ADDITIONAL_QUESTIONS" && <ScreenAdditionalQuestions />}
      {s.step === "SUMMARY" && <ScreenSummary onRunAnalysis={onRunAnalysis} isRunning={isRunning} />}
    </div>
  );
}
