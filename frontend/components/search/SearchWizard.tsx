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
  population: string[];
  innerSetting: string[];
  outcome: string[];
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
  population: { selected: string[]; noPreference: boolean };
  innerSetting: { selected: string[]; noPreference: boolean };
  outcome: { selected: string[]; noPreference: boolean };
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
  population: { selected: [], noPreference: true },
  innerSetting: { selected: [], noPreference: true },
  outcome: { selected: [], noPreference: true },
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
      population: { selected: [], noPreference: true },
      innerSetting: { selected: [], noPreference: true },
      outcome: { selected: [], noPreference: true },
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
    // Skip ADDITIONAL_QUESTIONS step - go directly from PARAMETERS to SUMMARY
    const steps: Step[] = ["ASK", "POPULATION", "INNER_SETTING", "OUTCOME", "SCREENING", "PARAMETERS", "ADDITIONAL_QUESTIONS", "SUMMARY"];
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
    // Skip ADDITIONAL_QUESTIONS step - go directly from SUMMARY to PARAMETERS
    const steps: Step[] = ["ASK", "POPULATION", "INNER_SETTING", "OUTCOME", "SCREENING", "PARAMETERS", "ADDITIONAL_QUESTIONS", "SUMMARY"];
    const currentIdx = steps.indexOf(s.step);
    if (currentIdx > 0) {
      const prevStep = steps[currentIdx - 1];
      // Skip ADDITIONAL_QUESTIONS - go directly to PARAMETERS
      if (prevStep === "ADDITIONAL_QUESTIONS") {
        set({ step: "PARAMETERS" });
      } else {
        set({ step: prevStep });
      }
    }
  },
  buildContext: () => {
    const s = get();
    return {
      researchQuestion: s.researchQuestion,
      population: s.population.noPreference ? [] : s.population.selected,
      innerSetting: s.innerSetting.noPreference ? [] : s.innerSetting.selected,
      outcome: s.outcome.noPreference ? [] : s.outcome.selected,
      implementationConstraints: s.implementationConstraints,
      parameters: s.parameters,
      screeningFactors: s.screeningFactors,
      additionalQuestions: s.additionalQuestions,
      maxResults: s.maxResults,
    };
  },
}));

// ---------------- HELPERS ----------------
function ProgressBar({
  step,
  researchQuestion,
  onStepClick,
}: {
  step: Step;
  researchQuestion: string;
  onStepClick: (s: Step) => void;
}) {
  const steps: { id: Step; label: string }[] = [
    { id: "ASK", label: "Question" },
    { id: "POPULATION", label: "Population" },
    { id: "INNER_SETTING", label: "Setting" },
    { id: "OUTCOME", label: "Outcome" },
    { id: "SCREENING", label: "Refinement" },
    { id: "PARAMETERS", label: "Filters" },
    { id: "SUMMARY", label: "Summary" },
  ];
  const currentIdx = steps.findIndex((s) => s.id === step);
  const canJump = !!researchQuestion.trim();

  return (
    <div className="w-full border-b border-gray-100 bg-white px-4 py-3">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-2">
        {steps.map((item, idx) => {
          const isCompleted = idx < currentIdx;
          const isCurrent = idx === currentIdx;
          const isClickable = canJump;
          return (
            <React.Fragment key={item.id}>
              <button
                type="button"
                onClick={() => isClickable && onStepClick(item.id)}
                disabled={!isClickable}
                className={cx(
                  "min-w-0 flex items-center gap-2 text-left transition",
                  isClickable
                    ? "cursor-pointer hover:opacity-80"
                    : "cursor-default"
                )}
              >
                <div
                  className={cx(
                    "flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ring-1",
                    isCompleted || isCurrent
                      ? "bg-blue-600 !text-white ring-blue-600"
                      : "bg-white text-gray-500 ring-gray-300"
                  )}
                >
                  {idx + 1}
                </div>
                <span
                  className={cx(
                    "hidden text-xs sm:inline",
                    isCurrent ? "font-semibold text-gray-900" : "text-gray-500"
                  )}
                >
                  {item.label}
                </span>
              </button>
              {idx < steps.length - 1 && (
                <div
                  className={cx(
                    "h-px flex-1",
                    idx < currentIdx ? "bg-blue-600" : "bg-gray-200"
                  )}
                />
              )}
            </React.Fragment>
          );
        })}
      </div>
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
  if (context.population.length > 0) {
    const popText = context.population.length === 1 
      ? context.population[0]
      : context.population.join(", ");
    parts.push(`for ${popText}`);
  }
  
  // Add outcome context
  if (context.outcome.length > 0) {
    const outcomeText = context.outcome.length === 1
      ? context.outcome[0]
      : context.outcome.join(", ");
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
        <div className="flex justify-end items-center mt-6">
          <Button 
            variant="secondary"
            className="!bg-[#A5D6E1] !text-black hover:!bg-[#93c9d6] border-0 ring-0"
            full 
            disabled={!s.researchQuestion.trim() || s.isGeneratingOptions} 
            onClick={handleNext}
          >
            {s.isGeneratingOptions ? (
              <span className="inline-flex items-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-black/30 border-t-black" />
                Generating options...
              </span>
            ) : 'Continue'}
          </Button>
        </div>
      </div>
    </div>
  );
}

function ScreenPopulation() {
  const s = useWizard();
  const [customInput, setCustomInput] = useState("");

  const togglePopulation = (pop: string) => {
    const current = s.population.selected;
    if (s.population.noPreference) {
      s.set({ population: { selected: [pop], noPreference: false } });
      return;
    }
    if (current.includes(pop)) {
      const next = current.filter(p => p !== pop);
      s.set({ population: { selected: next, noPreference: next.length === 0 } });
    } else {
      s.set({ population: { selected: [...current, pop], noPreference: false } });
    }
  };

  const selectNoPreference = () => {
    s.set({ population: { selected: [], noPreference: true } });
  };

  const addCustom = () => {
    const trimmed = customInput.trim();
    if (!trimmed) return;
    if (!s.population.selected.includes(trimmed)) {
      s.set({ population: { selected: [...s.population.selected, trimmed], noPreference: false } });
    }
    setCustomInput("");
  };

  const removePopulation = (pop: string) => {
    const next = s.population.selected.filter(p => p !== pop);
    s.set({ population: { selected: next, noPreference: next.length === 0 } });
  };

  const exampleOptions = s.generatedPopulationOptions.length > 0
    ? s.generatedPopulationOptions
    : [...FALLBACK_POPULATION_EXAMPLES];
  const customOptions = s.population.selected.filter(pop => !exampleOptions.includes(pop));

  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8 py-16">
      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Are you targeting a particular population?</h2>
        <p className="text-gray-600 text-lg">We use this to prioritise evidence for the populations you care about.</p>
      </div>

      <div className="space-y-6 max-w-2xl mx-auto">
        <div className="flex flex-col gap-3">
          <button
            type="button"
            onClick={selectNoPreference}
            className={cx(
              "w-full text-left px-4 py-4 rounded-xl transition ring-1 whitespace-normal break-words",
              s.population.noPreference
                ? "bg-blue-600 !text-white ring-blue-600"
                : "bg-white text-gray-900 ring-gray-300 hover:bg-gray-50"
            )}
          >
            No preference
          </button>

          <div className="flex items-center gap-3 py-1">
            <div className="h-px flex-1 bg-gray-200" />
            <span className="text-xs text-gray-500 uppercase tracking-wide">Or select specific populations</span>
            <div className="h-px flex-1 bg-gray-200" />
          </div>

          {exampleOptions.map((pop) => {
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
    <div className="max-w-4xl mx-auto space-y-8 p-8 pt-16 pb-6">
      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Are you interested in particular settings?</h2>
        <p className="text-gray-600 text-lg">We use this to prioritise context-matched evidence and assess transferability.</p>
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

    </div>
  );
}

function ScreenOutcome() {
  const s = useWizard();
  const [customInput, setCustomInput] = useState("");

  const toggleOutcome = (outcome: string) => {
    const current = s.outcome.selected;
    if (s.outcome.noPreference) {
      s.set({ outcome: { selected: [outcome], noPreference: false } });
      return;
    }
    if (current.includes(outcome)) {
      const next = current.filter(o => o !== outcome);
      s.set({ outcome: { selected: next, noPreference: next.length === 0 } });
    } else {
      s.set({ outcome: { selected: [...current, outcome], noPreference: false } });
    }
  };

  const selectNoPreference = () => {
    s.set({ outcome: { selected: [], noPreference: true } });
  };

  const addCustom = () => {
    const trimmed = customInput.trim();
    if (!trimmed) return;
    if (!s.outcome.selected.includes(trimmed)) {
      s.set({ outcome: { selected: [...s.outcome.selected, trimmed], noPreference: false } });
    }
    setCustomInput("");
  };

  const removeOutcome = (outcome: string) => {
    const next = s.outcome.selected.filter(o => o !== outcome);
    s.set({ outcome: { selected: next, noPreference: next.length === 0 } });
  };

  const exampleOptions = s.generatedOutcomeOptions.length > 0
    ? s.generatedOutcomeOptions
    : [...FALLBACK_OUTCOME_EXAMPLES];
  const customOptions = s.outcome.selected.filter(outcome => !exampleOptions.includes(outcome));

  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8 py-16">
      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Are you interested in particular outcomes?</h2>
        <p className="text-gray-600 text-lg">We use this to prioritise evidence measuring your outcomes of interest.</p>
      </div>

      <div className="space-y-6 max-w-2xl mx-auto">
        <div className="flex flex-col gap-3">
          <button
            type="button"
            onClick={selectNoPreference}
            className={cx(
              "w-full text-left px-4 py-4 rounded-xl transition ring-1 whitespace-normal break-words",
              s.outcome.noPreference
                ? "bg-blue-600 !text-white ring-blue-600"
                : "bg-white text-gray-900 ring-gray-300 hover:bg-gray-50"
            )}
          >
            No preference
          </button>

          <div className="flex items-center gap-3 py-1">
            <div className="h-px flex-1 bg-gray-200" />
            <span className="text-xs text-gray-500 uppercase tracking-wide">Or select specific outcomes</span>
            <div className="h-px flex-1 bg-gray-200" />
          </div>

          {exampleOptions.map((outcome) => {
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

    </div>
  );
}

function ScreenParameters() {
  const s = useWizard();
  const [selectedCountry, setSelectedCountry] = useState("");
  const hasSelectedSource =
    s.parameters.access.academic || s.parameters.access.policy;
  const hasInvalidCustomDateRange =
    s.parameters.timePreset === "CUSTOM" &&
    !!s.parameters.customFrom &&
    !!s.parameters.customTo &&
    s.parameters.customFrom > s.parameters.customTo;

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
    const next = s.parameters.geography.filter(x => x !== g);
    s.set({
      parameters: {
        ...s.parameters,
        geography: next.length > 0 ? next : [ANYWHERE_VALUE],
      },
    });
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
        <p className="text-gray-600 text-lg">We use these filters to narrow the evidence set before ranking.</p>
      </div>

      <div className="space-y-8 max-w-2xl mx-auto">
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
          {!hasSelectedSource && (
            <p className="text-sm text-red-600">
              Select at least one source to continue.
            </p>
          )}
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
            <div className="rounded-2xl border border-blue-100 bg-blue-50/40 p-4 space-y-3">
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
              {hasInvalidCustomDateRange && (
                <p className="text-sm text-red-600">
                  End date must be the same as or later than the start date.
                </p>
              )}
            </div>
          )}
        </div>

        {/* Geography */}
        <div className="space-y-4">
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

      </div>

    </div>
  );
}

function ScreenScreening() {
  const s = useWizard();
  const [customInput, setCustomInput] = useState("");
  const constraintOptions = ["Any", "Low", "Moderate", "High"];

  const addFactor = () => {
    if (customInput.trim() && !s.screeningFactors.includes(customInput.trim())) {
      s.set({ screeningFactors: [...s.screeningFactors, customInput.trim()] });
      setCustomInput("");
    }
  };

  const removeFactor = (factor: string) => {
    s.set({ screeningFactors: s.screeningFactors.filter(f => f !== factor) });
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8 py-16">
      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Additional criteria</h2>
        <p className="text-gray-600 text-lg">
          Optional additional considerations for evidence assessment.
        </p>
      </div>

      <div className="space-y-6 max-w-2xl mx-auto">
        <div className="space-y-4">
          <h3 className="font-semibold text-lg">Implementation constraints</h3>
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <span>Set your tolerance on implementation factors. This will be used during impact and transferability assessment.</span>
            <Tooltip
              content={
                <div className="max-w-xs text-sm space-y-1">
                  <p><span className="font-medium">Low</span>: minimal resources or operational effort capacity.</p>
                  <p><span className="font-medium">Moderate</span>: manageable resources and coordination capacity.</p>
                  <p><span className="font-medium">High</span>: substantial resources, staffing, or delivery capacity.</p>
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

        <div className="h-px bg-gray-100" />

        <div className="space-y-3">
          <h3 className="font-semibold text-lg">Additional screening factors</h3>
          <p className="text-sm text-gray-600">
            Add any other criteria that you think are important to consider when screening the evidence.
          </p>
        </div>

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

    </div>
  );
}

function ScreenSummary({ isRunning = false }: { isRunning?: boolean }) {
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
          <CardTitle>Search settings</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-4">
            <button
              type="button"
              onClick={() => goToStep("POPULATION")}
              className="rounded-xl border border-gray-200 bg-gray-50/50 p-4 text-left transition hover:bg-gray-50"
            >
              <div className="text-xs uppercase tracking-wide text-gray-500 mb-1">Population</div>
              {context.population.length > 0 ? (
                <p className="text-gray-900">{context.population.join(", ")}</p>
              ) : (
                <p className="text-gray-500">No preference</p>
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
              {context.outcome.length > 0 ? (
                <p className="text-gray-900">{context.outcome.join(", ")}</p>
              ) : (
                <p className="text-gray-500">No preference</p>
              )}
            </button>
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-3">
            <div className="text-xs uppercase tracking-wide text-gray-500">Refinement</div>
            <button type="button" onClick={() => goToStep("SCREENING")} className="block w-full text-left rounded-lg p-1 transition hover:bg-gray-50">
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
                <div className="mt-2 text-gray-500">No preference</div>
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
                    <span className="text-gray-500">None selected</span>
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
                    <span className="text-gray-500">No preference</span>
                  )}
                </div>
              </button>
            </div>
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
  const context = s.buildContext();
  const hasSelectedSource = context.parameters.sources.length > 0;
  const hasInvalidCustomDateRange =
    context.parameters.timePreset === "CUSTOM" &&
    !!context.parameters.customFrom &&
    !!context.parameters.customTo &&
    context.parameters.customFrom > context.parameters.customTo;

  const isSummaryStep = s.step === "SUMMARY";
  const showActionBar = s.step !== "ASK";

  const getPrimaryAction = () => {
    if (isSummaryStep) {
      return {
        label: isRunning ? "Starting up..." : "Run Analysis",
        onClick: () => onRunAnalysis(context),
        disabled: isRunning || !hasSelectedSource || hasInvalidCustomDateRange,
      };
    }

    if (s.step === "SCREENING") {
      return {
        label: s.isGeneratingOptions ? "Generating..." : "Next",
        onClick: () => s.next(),
        disabled: s.isGeneratingOptions,
      };
    }

    if (s.step === "PARAMETERS") {
      return {
        label: "Next",
        onClick: () => s.next(),
        disabled: !hasSelectedSource || hasInvalidCustomDateRange,
      };
    }

    return {
      label: "Next",
      onClick: () => s.next(),
      disabled: false,
    };
  };

  const primaryAction = getPrimaryAction();

  return (
    <div className="bg-white text-gray-900 min-h-[calc(100vh-8rem)] flex flex-col">
      <ProgressBar
        step={s.step}
        researchQuestion={s.researchQuestion}
        onStepClick={(step) => s.set({ step })}
      />
      <div className="flex-1">
        {s.step === "ASK" && <ScreenAsk />}
        {s.step === "POPULATION" && <ScreenPopulation />}
        {s.step === "INNER_SETTING" && <ScreenInnerSetting />}
        {s.step === "OUTCOME" && <ScreenOutcome />}
        {s.step === "SCREENING" && <ScreenScreening />}
        {s.step === "PARAMETERS" && <ScreenParameters />}
        {s.step === "ADDITIONAL_QUESTIONS" && <ScreenAdditionalQuestions />}
        {s.step === "SUMMARY" && <ScreenSummary isRunning={isRunning} />}
      </div>

      {showActionBar && (
        <div className="mt-auto max-w-4xl mx-auto w-full px-8">
          <div className="flex justify-between items-center rounded-2xl border border-gray-200 bg-gray-50 p-4">
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={() => s.back()} disabled={isRunning}>Back</Button>
              <Button variant="secondary" onClick={() => s.reset()} disabled={isRunning}>
                {isSummaryStep ? "Start new search" : "Restart"}
              </Button>
            </div>
            <Button
              variant="secondary"
              className="!bg-[#A5D6E1] !text-black hover:!bg-[#93c9d6] border-0 ring-0"
              onClick={primaryAction.onClick}
              disabled={primaryAction.disabled}
            >
              {primaryAction.label}
            </Button>
          </div>

          {isSummaryStep && !hasSelectedSource && (
            <p className="mt-2 text-sm text-red-600 text-right">
              Select at least one search source before running analysis.
            </p>
          )}
          {isSummaryStep && hasInvalidCustomDateRange && (
            <p className="mt-2 text-sm text-red-600 text-right">
              Fix your custom date range before running analysis.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
