import { NextResponse } from "next/server";
import { getAnnouncements, getLastUpdated } from "@/lib/data-loader";

export async function GET() {
  const [data, updatedAt] = await Promise.all([getAnnouncements(), getLastUpdated()]);
  return NextResponse.json({ data, updatedAt });
}
