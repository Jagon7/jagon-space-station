import { NextResponse } from "next/server";
import { getDispositionStocks, getLastUpdated } from "@/lib/data-loader";

export const dynamic = "force-static";

export async function GET() {
  const [data, updatedAt] = await Promise.all([getDispositionStocks(), getLastUpdated()]);
  return NextResponse.json({ data, updatedAt });
}
