import { NextResponse } from "next/server";
import { getNoticeStocks, getLastUpdated } from "@/lib/data-loader";

export async function GET() {
  const [data, updatedAt] = await Promise.all([getNoticeStocks(), getLastUpdated()]);
  return NextResponse.json({ data, updatedAt });
}
