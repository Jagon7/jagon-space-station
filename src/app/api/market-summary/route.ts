import { NextResponse } from "next/server";
import { getMarketSummary, getSectors, getLastUpdated } from "@/lib/data-loader";

export async function GET() {
  const [summary, sectors, updatedAt] = await Promise.all([getMarketSummary(), getSectors(), getLastUpdated()]);
  return NextResponse.json({ ...summary, sectors, updatedAt });
}
