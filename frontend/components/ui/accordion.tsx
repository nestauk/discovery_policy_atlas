"use client";

import * as React from "react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "./collapsible";

type AccordionProps = React.HTMLAttributes<HTMLDivElement> & {
  type?: "single" | "multiple";
  collapsible?: boolean;
};

function Accordion(props: AccordionProps) {
  return <div data-slot="accordion" {...props} />;
}

type AccordionItemProps = React.ComponentProps<typeof Collapsible> & {
  value?: string;
};

function AccordionItem(props: AccordionItemProps) {
  return <Collapsible data-slot="accordion-item" {...props} />;
}

function AccordionTrigger(
  props: React.ComponentProps<typeof CollapsibleTrigger>
) {
  return (
    <CollapsibleTrigger data-slot="accordion-trigger" {...props} />
  );
}

function AccordionContent(
  props: React.ComponentProps<typeof CollapsibleContent>
) {
  return (
    <CollapsibleContent data-slot="accordion-content" {...props} />
  );
}

export { Accordion, AccordionItem, AccordionTrigger, AccordionContent };


