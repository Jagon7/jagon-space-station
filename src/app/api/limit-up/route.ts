import { NextResponse } from "next/server";
import { getLimitUpStocks, getLastUpdated } from "@/lib/data-loader";

export async function GET() {
  const [data, updatedAt] = await Promise.all([getLimitUpStocks(), getLastUpdated()]);
  return NextResponse.json({ data, updatedAt });
}
